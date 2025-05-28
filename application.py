# /root/DEATHBILL/urls.py
from flask import Blueprint, jsonify, request, render_template
from .application import db, Bill, Comment, Reply, Evidence, Tweet, TweetComment, get_user_token, user_voted_bills, user_liked_comments, user_liked_tweets, user_retweeted_tweets, allowed_file, MAX_FILE_SIZE

# Blueprint 定義
main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__, url_prefix='/api')

# ルートエンドポイント
@main_bp.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.exception(f"Error rendering index at {request.url}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

# 議案一覧取得
@api_bp.route('/bills', methods=['GET'])
def get_bills():
    try:
        bills = Bill.query.order_by(Bill.timestamp.desc()).all()
        return jsonify([{
            "id": bill.id,
            "title": bill.title,
            "support": bill.support,
            "against": bill.against,
            "description": bill.description,
            "timestamp": bill.timestamp * 1000,
            "comments": [{
                "id": comment.id,
                "content": comment.content,
                "timestamp": comment.timestamp * 1000,
                "goodCount": comment.good_count,
                "replies": [{"content": reply.content, "timestamp": reply.timestamp * 1000} for reply in comment.replies],
                "file": {"name": comment.file.name, "type": comment.file.type, "url": comment.file.file_url} if comment.file and comment.file.file_url else None
            } for comment in bill.comments],
            "evidence": [{"name": evidence.name, "type": evidence.type, "url": evidence.file_url} for evidence in bill.evidence if evidence.file_url]
        } for bill in bills])
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching bills at {request.url}: {str(e)}")
        return jsonify({"error": "Database error"}), 500

# 個別議案取得
@api_bp.route('/bills/<int:bill_id>', methods=['GET'])
def get_bill(bill_id):
    try:
        bill = Bill.query.get(bill_id)
        if bill:
            return jsonify({
                "id": bill.id,
                "title": bill.title,
                "support": bill.support,
                "against": bill.against,
                "description": bill.description,
                "timestamp": bill.timestamp * 1000,
                "comments": [{
                    "id": comment.id,
                    "content": comment.content,
                    "timestamp": comment.timestamp * 1000,
                    "goodCount": comment.good_count,
                    "replies": [{"content": reply.content, "timestamp": reply.timestamp * 1000} for reply in comment.replies],
                    "file": {"name": comment.file.name, "type": comment.file.type, "url": comment.file.file_url} if comment.file and comment.file.file_url else None
                } for comment in bill.comments],
                "evidence": [{"name": evidence.name, "type": evidence.type, "url": evidence.file_url} for evidence in bill.evidence if evidence.file_url]
            })
        return jsonify({"error": "Bill not found"}), 404
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching bill {bill_id} at {request.url}: {str(e)}")
        return jsonify({"error": "Database error"}), 500

# 議案に投票
@api_bp.route('/bills/<int:bill_id>/vote', methods=['POST'])
def vote_bill(bill_id):
    user_token = get_user_token()
    user_voted = user_voted_bills.setdefault(user_token, set())
    if bill_id in user_voted:
        return jsonify({"error": "Already voted on this bill"}), 400
    try:
        bill = Bill.query.get(bill_id)
        if not bill:
            return jsonify({"error": "Bill not found"}), 404
        vote_type = request.json.get('type')
        if vote_type == 'support':
            bill.support += 1
        elif vote_type == 'against':
            bill.against += 1
        else:
            return jsonify({"error": "Invalid vote type"}), 400
        user_voted.add(bill_id)
        db.session.commit()
        return jsonify({
            "id": bill.id,
            "title": bill.title,
            "support": bill.support,
            "against": bill.against,
            "description": bill.description,
            "timestamp": bill.timestamp * 1000,
            "comments": [{
                "id": comment.id,
                "content": comment.content,
                "timestamp": comment.timestamp * 1000,
                "goodCount": comment.good_count,
                "replies": [{"content": reply.content, "timestamp": reply.timestamp * 1000} for reply in comment.replies],
                "file": {"name": comment.file.name, "type": comment.file.type, "url": comment.file.file_url} if comment.file and comment.file.file_url else None
            } for comment in bill.comments],
            "evidence": [{"name": evidence.name, "type": evidence.type, "url": evidence.file_url} for evidence in bill.evidence if evidence.file_url]
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error voting on bill {bill_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

# 議案にコメント追加
@api_bp.route('/bills/<int:bill_id>/comments', methods=['POST'])
def add_comment(bill_id):
    try:
        bill = Bill.query.get(bill_id)
        if not bill:
            return jsonify({"error": "Bill not found"}), 404
        comment_text = request.form.get('content')
        file = request.files.get('file')
        new_comment = Comment(
            bill_id=bill_id,
            content=comment_text,
            timestamp=int(time.time()),
            good_count=0
        )
        if file:
            if file.content_length > MAX_FILE_SIZE:
                return jsonify({"error": "File too large (max 5MB)"}), 400
            if not allowed_file(file.filename):
                return jsonify({"error": "Invalid file type (JPEG, PNG, GIF only)"}), 400
            filename = f"{bill_id}_{int(time.time())}_{file.filename}"
            file_path = os.path.join(application.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            file_url = f"/{application.config['UPLOAD_FOLDER']}/{filename}"
            evidence = Evidence(
                bill_id=bill_id,
                name=file.filename,
                type=file.content_type,
                file_url=file_url
            )
            db.session.add(evidence)
            db.session.flush()
            new_comment.file_id = evidence.id
            logger.info(f"Saved file to {file_path}")
        db.session.add(new_comment)
        db.session.commit()
        return jsonify({
            "id": new_comment.id,
            "content": new_comment.content,
            "timestamp": new_comment.timestamp * 1000,
            "goodCount": new_comment.good_count,
            "replies": [],
            "file": {"name": new_comment.file.name, "type": new_comment.file.type, "url": new_comment.file.file_url} if new_comment.file and new_comment.file.file_url else None
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error adding comment to bill {bill_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.exception(f"Error processing file upload at {request.url}: {str(e)}")
        return jsonify({"error": "File upload error"}), 500

# コメントにリプライ追加
@api_bp.route('/bills/<int:bill_id>/comments/<int:comment_id>/replies', methods=['POST'])
def add_comment_reply(bill_id, comment_id):
    try:
        comment = Comment.query.get(comment_id)
        if not comment or comment.bill_id != bill_id:
            return jsonify({"error": "Comment or bill not found"}), 404
        reply_text = request.json.get('content')
        if not reply_text:
            return jsonify({"error": "Reply content is required"}), 400
        new_reply = Reply(
            comment_id=comment_id,
            content=reply_text,
            timestamp=int(time.time())
        )
        db.session.add(new_reply)
        db.session.commit()
        return jsonify({
            "content": new_reply.content,
            "timestamp": new_reply.timestamp * 1000
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error adding reply to comment {comment_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

# コメントにいいね
@api_bp.route('/bills/<int:bill_id>/comments/<int:comment_id>/good', methods=['POST'])
def good_comment(bill_id, comment_id):
    user_token = get_user_token()
    user_liked = user_liked_comments.setdefault(user_token, set())
    comment_key = f"{bill_id}-{comment_id}"
    if comment_key in user_liked:
        return jsonify({"error": "Already liked this comment"}), 400
    try:
        comment = Comment.query.get(comment_id)
        if not comment or comment.bill_id != bill_id:
            return jsonify({"error": "Comment or bill not found"}), 404
        comment.good_count += 1
        user_liked.add(comment_key)
        db.session.commit()
        return jsonify({
            "id": comment.id,
            "content": comment.content,
            "timestamp": comment.timestamp * 1000,
            "goodCount": comment.good_count,
            "replies": [{"content": reply.content, "timestamp": reply.timestamp * 1000} for reply in comment.replies],
            "file": {"name": comment.file.name, "type": comment.file.type, "url": comment.file.file_url} if comment.file and comment.file.file_url else None
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error liking comment {comment_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

# ツイート操作（取得と投稿）
@api_bp.route('/tweets', methods=['GET', 'POST'])
def handle_tweets():
    try:
        if request.method == 'GET':
            tweets = Tweet.query.order_by(Tweet.timestamp.desc()).all()
            return jsonify([{
                "id": tweet.id,
                "username": tweet.username,
                "content": tweet.content,
                "timestamp": tweet.timestamp * 1000,
                "retweetCount": tweet.retweet_count,
                "goodCount": tweet.good_count,
                "comments": [{"content": comment.content, "timestamp": comment.timestamp * 1000} for comment in tweet.comments],
                "file": {"name": tweet.file.name, "type": tweet.file.type, "url": tweet.file.file_url} if tweet.file and tweet.file.file_url else None
            } for tweet in tweets])
        else:  # POST
            tweet_text = request.form.get('content')
            file = request.files.get('file')
            new_tweet = Tweet(
                username="👤",
                content=tweet_text,
                timestamp=int(time.time()),
                retweet_count=0,
                good_count=0
            )
            db.session.add(new_tweet)
            db.session.flush()
            if file:
                if file.content_length > MAX_FILE_SIZE:
                    return jsonify({"error": "File too large (max 5MB)"}), 400
                if not allowed_file(file.filename):
                    return jsonify({"error": "Invalid file type (JPEG, PNG, GIF only)"}), 400
                filename = f"tweet_{new_tweet.id}_{int(time.time())}_{file.filename}"
                file_path = os.path.join(application.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                file_url = f"/{application.config['UPLOAD_FOLDER']}/{filename}"
                evidence = Evidence(
                    name=file.filename,
                    type=file.content_type,
                    file_url=file_url
                )
                db.session.add(evidence)
                db.session.flush()
                new_tweet.file_id = evidence.id
                logger.info(f"Saved file to {file_path}")
            db.session.commit()
            return jsonify({
                "id": new_tweet.id,
                "username": new_tweet.username,
                "content": new_tweet.content,
                "timestamp": new_tweet.timestamp * 1000,
                "retweetCount": new_tweet.retweet_count,
                "goodCount": new_tweet.good_count,
                "comments": [],
                "file": {"name": new_tweet.file.name, "type": new_tweet.file.type, "url": new_tweet.file.file_url} if new_tweet.file and new_tweet.file.file_url else None
            })
    except SQLAlchemyError as e:
        logger.exception(f"Error handling tweets at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.exception(f"Error processing file upload at {request.url}: {str(e)}")
        return jsonify({"error": "File upload error"}), 500

# ツイートにコメント追加
@api_bp.route('/tweets/<int:tweet_id>/comments', methods=['POST'])
def add_tweet_comment(tweet_id):
    try:
        tweet = Tweet.query.get(tweet_id)
        if not tweet:
            return jsonify({"error": "Tweet not found"}), 404
        comment_text = request.json.get('content')
        if not comment_text:
            return jsonify({"error": "Comment content is required"}), 400
        new_comment = TweetComment(
            tweet_id=tweet_id,
            content=comment_text,
            timestamp=int(time.time())
        )
        db.session.add(new_comment)
        db.session.commit()
        return jsonify({
            "content": new_comment.content,
            "timestamp": new_comment.timestamp * 1000
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error adding comment to tweet {tweet_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

# ツイートにいいね
@api_bp.route('/tweets/<int:tweet_id>/good', methods=['POST'])
def good_tweet(tweet_id):
    try:
        user_token = get_user_token()
        user_liked = user_liked_tweets.setdefault(user_token, set())
        if tweet_id in user_liked:
            return jsonify({"error": "Already liked this tweet"}), 400
        tweet = Tweet.query.get(tweet_id)
        if not tweet:
            return jsonify({"error": "Tweet not found"}), 404
        tweet.good_count += 1
        user_liked.add(tweet_id)
        db.session.commit()
        return jsonify({
            "id": tweet.id,
            "username": tweet.username,
            "content": tweet.content,
            "timestamp": tweet.timestamp * 1000,
            "retweetCount": tweet.retweet_count,
            "goodCount": tweet.good_count,
            "comments": [{"content": comment.content, "timestamp": comment.timestamp * 1000} for comment in tweet.comments],
            "file": {"name": tweet.file.name, "type": tweet.file.type, "url": tweet.file.file_url} if tweet.file and tweet.file.file_url else None
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error liking tweet {tweet_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

# ツイートをリツイート
@api_bp.route('/tweets/<int:tweet_id>/retweet', methods=['POST'])
def retweet_tweet(tweet_id):
    user_token = get_user_token()
    user_retweets = user_retweeted_tweets.setdefault(user_token, set())
    if tweet_id in user_retweets:
        return jsonify({"error": "Already retweeted this tweet"}), 400
    try:
        tweet = Tweet.query.get(tweet_id)
        if not tweet:
            return jsonify({"error": "Tweet not found"}), 404
        tweet.retweet_count += 1
        user_retweets.add(tweet_id)
        db.session.commit()
        return jsonify({
            "id": tweet.id,
            "username": tweet.username,
            "content": tweet.content,
            "timestamp": tweet.timestamp * 1000,
            "retweetCount": tweet.retweet_count,
            "goodCount": tweet.good_count,
            "comments": [{"content": comment.content, "timestamp": comment.timestamp * 1000} for comment in tweet.comments],
            "file": {"name": tweet.file.name, "type": tweet.file.type, "url": tweet.file.file_url} if tweet.file and tweet.file.file_url else None
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error retweeting tweet {tweet_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

# Blueprintを登録するためのリスト
blueprints = [
    (main_bp, ''),
    (api_bp, '/api')
]
