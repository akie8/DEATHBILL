from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
import time
import os
import logging
from retrying import retry
import pymysql.err
import uuid  # 追加: get_user_token()で必要

# 環境変数を読み込み
load_dotenv()

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

application = Flask(__name__, static_folder='static', template_folder='templates')

# CORS設定（開発用にワイルドカード、本番ではdeathbill.earthに制限）
CORS(application, resources={r"/api/*": {"origins": "*"}})

# 環境変数のチェック
required_env_vars = ['DB_USERNAME', 'DB_PASSWORD', 'DB_HOST', 'DB_NAME']
missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    logger.error(f"Missing environment variables: {missing_vars}")
    raise EnvironmentError(f"Missing environment variables: {missing_vars}")

# データベース設定（Xserver VPSのローカルMySQL）
application.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{os.environ['DB_USERNAME']}:{os.environ['DB_PASSWORD']}"
    f"@{os.environ['DB_HOST']}:3306/{os.environ['DB_NAME']}"
)
application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
application.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'max_overflow': 10,
    'pool_timeout': 30,
    'pool_recycle': 1800,
    'pool_pre_ping': True,
    'connect_args': {'connect_timeout': 10}  # 修正: connect_timeoutをconnect_args内に移動
}
db = SQLAlchemy(application)

# アップロードフォルダ設定
UPLOAD_FOLDER = 'static/uploads'
application.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# データベースモデル
class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    support = db.Column(db.Integer, default=0)
    against = db.Column(db.Integer, default=0)
    description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)
    comments = db.relationship('Comment', backref='bill', lazy=True)
    evidence = db.relationship('Evidence', backref='bill', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    content = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.Integer, nullable=False)
    good_count = db.Column(db.Integer, default=0)
    replies = db.relationship('Reply', backref='comment', lazy=True)
    file_id = db.Column(db.Integer, db.ForeignKey('evidence.id'), nullable=True)

class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)

class Evidence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=True)
    name = db.Column(db.String(200), nullable=True)
    type = db.Column(db.String(100), nullable=True)
    file_url = db.Column(db.String(200), nullable=True)  # S3のs3_keyをfile_urlに変更

class Tweet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.Integer, nullable=False)
    retweet_count = db.Column(db.Integer, default=0)
    good_count = db.Column(db.Integer, default=0)
    file_id = db.Column(db.Integer, db.ForeignKey('evidence.id'), nullable=True)
    comments = db.relationship('TweetComment', backref='tweet', lazy=True)

class TweetComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tweet_id = db.Column(db.Integer, db.ForeignKey('tweet.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)

# ファイル拡張子チェック
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# データベース初期化
@retry(
    stop_max_attempt_number=5,
    wait_fixed=10000,
    retry_on_exception=lambda e: isinstance(e, (SQLAlchemyError, pymysql.err.OperationalError))
)
def initialize_database():
    try:
        logger.info("Initializing database...")
        db.create_all()
        with db.session.no_autoflush:
            if not Bill.query.first():
                bills = [
                    Bill(id=1, title="Free Public Transport Initiative", support=12245, against=3128,
                         description="This bill proposes to make all public transportation free for citizens.", timestamp=int(time.time()) - 3600),  # 修正: ミリ秒→秒、3600000→3600
                    Bill(id=2, title="Global Education Budget Increase", support=28791, against=1552,
                         description="This bill proposes a 15% increase in the global education budget.", timestamp=int(time.time()) - 1800),  # 修正: ミリ秒→秒、1800000→1800
                    Bill(id=3, title="Universal Healthcare Access", support=35762, against=8901,
                         description="A comprehensive plan to provide universal healthcare coverage.", timestamp=int(time.time()) - 7200)  # 修正: ミリ秒→秒、7200000→7200
                ]
                db.session.bulk_save_objects(bills)
                logger.info("Inserted initial bills")
            if not Tweet.query.first():
                tweets = [
                    Tweet(id=1, username="👤", content="Politician X proposed a policy to cut public transport funding. Total trash! 🗑️",
                          timestamp=int(time.time()) - 3600, retweet_count=0, good_count=0),  # 修正: ミリ秒→秒、3600000→3600
                    Tweet(id=2, username="👤", content="Heard about a new tax break for the ultra-rich? Another garbage policy! 😡",
                          timestamp=int(time.time()) - 1800, retweet_count=0, good_count=0)  # 修正: ミリ秒→秒、1800000→1800
                ]
                db.session.bulk_save_objects(tweets)
                tweet_comments = [
                    TweetComment(tweet_id=1, content="That’s awful! We need more funding, not less!", timestamp=int(time.time()) - 3300),  # 修正: ミリ秒→秒、3300000→3300
                    TweetComment(tweet_id=1, content="Classic politician move.", timestamp=int(time.time()) - 3000)  # 修正: ミリ秒→秒、3000000→3000
                ]
                db.session.bulk_save_objects(tweet_comments)
                logger.info("Inserted initial tweets and comments")
            db.session.commit()
        logger.info("Database initialized successfully")
    except (SQLAlchemyError, pymysql.err.OperationalError) as e:
        logger.error(f"Database initialization failed: {str(e)}")
        db.session.rollback()
        raise

# 初回起動時に初期化
with application.app_context():
    try:
        initialize_database()
    except Exception as e:
        logger.exception(f"Initialization error: {str(e)}")
        raise

# 簡易セッション管理
def get_user_token():
    return request.headers.get('X-User-Token', str(uuid.uuid4()))

user_voted_bills = {}
user_liked_comments = {}
user_liked_tweets = {}
user_retweeted_tweets = {}

@application.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.exception(f"Error rendering index at {request.url}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@application.route('/api/bills', methods=['GET'])
def get_bills():
    try:
        bills = Bill.query.order_by(Bill.timestamp.desc()).all()
        return jsonify([{
            "id": bill.id,
            "title": bill.title,
            "support": bill.support,
            "against": bill.against,
            "description": bill.description,
            "timestamp": bill.timestamp * 1000,  # 修正: UIでミリ秒表示
            "comments": [{
                "id": comment.id,
                "content": comment.content,
                "timestamp": comment.timestamp * 1000,  # 修正: UIでミリ秒表示
                "goodCount": comment.good_count,
                "replies": [{"content": reply.content, "timestamp": reply.timestamp * 1000} for reply in comment.replies],  # 修正: UIでミリ秒表示
                "file": {"name": comment.file.name, "type": comment.file.type, "url": comment.file.file_url} if comment.file and comment.file.file_url else None
            } for comment in bill.comments],
            "evidence": [{"name": evidence.name, "type": evidence.type, "url": evidence.file_url} for evidence in bill.evidence if evidence.file_url]
        } for bill in bills])
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching bills at {request.url}: {str(e)}")
        return jsonify({"error": "Database error"}), 500

@application.route('/api/bills/<int:bill_id>', methods=['GET'])
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
                "timestamp": bill.timestamp * 1000,  # 修正: UIでミリ秒表示
                "comments": [{
                    "id": comment.id,
                    "content": comment.content,
                    "timestamp": comment.timestamp * 1000,  # 修正: UIでミリ秒表示
                    "goodCount": comment.good_count,
                    "replies": [{"content": reply.content, "timestamp": reply.timestamp * 1000} for reply in comment.replies],  # 修正: UIでミリ秒表示
                    "file": {"name": comment.file.name, "type": comment.file.type, "url": comment.file.file_url} if comment.file and comment.file.file_url else None
                } for comment in bill.comments],
                "evidence": [{"name": evidence.name, "type": evidence.type, "url": evidence.file_url} for evidence in bill.evidence if evidence.file_url]
            })
        return jsonify({"error": "Bill not found"}), 404
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching bill {bill_id} at {request.url}: {str(e)}")
        return jsonify({"error": "Database error"}), 500

@application.route('/api/bills/<int:bill_id>/vote', methods=['POST'])
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
            "timestamp": bill.timestamp * 1000,  # 修正: UIでミリ秒表示
            "comments": [{
                "id": comment.id,
                "content": comment.content,
                "timestamp": comment.timestamp * 1000,  # 修正: UIでミリ秒表示
                "goodCount": comment.good_count,
                "replies": [{"content": reply.content, "timestamp": reply.timestamp * 1000} for reply in comment.replies],  # 修正: UIでミリ秒表示
                "file": {"name": comment.file.name, "type": comment.file.type, "url": comment.file.file_url} if comment.file and comment.file.file_url else None
            } for comment in bill.comments],
            "evidence": [{"name": evidence.name, "type": evidence.type, "url": evidence.file_url} for evidence in bill.evidence if evidence.file_url]
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error voting on bill {bill_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

@application.route('/api/bills/<int:bill_id>/comments', methods=['POST'])
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
            timestamp=int(time.time()),  # 修正: ミリ秒→秒
            good_count=0
        )
        if file:
            if file.content_length > MAX_FILE_SIZE:
                return jsonify({"error": "File too large (max 5MB)"}), 400
            if not allowed_file(file.filename):
                return jsonify({"error": "Invalid file type (JPEG, PNG, GIF only)"}), 400
            filename = f"{bill_id}_{int(time.time())}_{file.filename}"  # 修正: ミリ秒→秒
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
            "timestamp": new_comment.timestamp * 1000,  # 修正: UIでミリ秒表示
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

@application.route('/api/bills/<int:bill_id>/comments/<int:comment_id>/replies', methods=['POST'])
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
            timestamp=int(time.time())  # 修正: ミリ秒→秒
        )
        db.session.add(new_reply)
        db.session.commit()
        return jsonify({
            "content": new_reply.content,
            "timestamp": new_reply.timestamp * 1000  # 修正: UIでミリ秒表示
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error adding reply to comment {comment_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

@application.route('/api/bills/<int:bill_id>/comments/<int:comment_id>/good', methods=['POST'])
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
            "timestamp": comment.timestamp * 1000,  # 修正: UIでミリ秒表示
            "goodCount": comment.good_count,
            "replies": [{"content": reply.content, "timestamp": reply.timestamp * 1000} for reply in comment.replies],  # 修正: UIでミリ秒表示
            "file": {"name": comment.file.name, "type": comment.file.type, "url": comment.file.file_url} if comment.file and comment.file.file_url else None
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error liking comment {comment_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

@application.route('/api/tweets', methods=['GET', 'POST'])
def handle_tweets():
    try:
        if request.method == 'GET':
            tweets = Tweet.query.order_by(Tweet.timestamp.desc()).all()
            return jsonify([{
                "id": tweet.id,
                "username": tweet.username,
                "content": tweet.content,
                "timestamp": tweet.timestamp * 1000,  # 修正: UIでミリ秒表示
                "retweetCount": tweet.retweet_count,
                "goodCount": tweet.good_count,
                "comments": [{"content": comment.content, "timestamp": comment.timestamp * 1000} for comment in tweet.comments],  # 修正: UIでミリ秒表示
                "file": {"name": tweet.file.name, "type": tweet.file.type, "url": tweet.file.file_url} if tweet.file and tweet.file.file_url else None
            } for tweet in tweets])
        else:  # POST
            tweet_text = request.form.get('content')
            file = request.files.get('file')
            new_tweet = Tweet(
                username="👤",
                content=tweet_text,
                timestamp=int(time.time()),  # 修正: ミリ秒→秒
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
                filename = f"tweet_{new_tweet.id}_{int(time.time())}_{file.filename}"  # 修正: ミリ秒→秒
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
                "timestamp": new_tweet.timestamp * 1000,  # 修正: UIでミリ秒表示
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

@application.route('/api/tweets/<int:tweet_id>/comments', methods=['POST'])
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
            timestamp=int(time.time())  # 修正: ミリ秒→秒
        )
        db.session.add(new_comment)
        db.session.commit()
        return jsonify({
            "content": new_comment.content,
            "timestamp": new_comment.timestamp * 1000  # 修正: UIでミリ秒表示
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error adding comment to tweet {tweet_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

@application.route('/api/tweets/<int:tweet_id>/good', methods=['POST'])
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
            "timestamp": tweet.timestamp * 1000,  # 修正: UIでミリ秒表示
            "retweetCount": tweet.retweet_count,
            "goodCount": tweet.good_count,
            "comments": [{"content": comment.content, "timestamp": comment.timestamp * 1000} for comment in tweet.comments],  # 修正: UIでミリ秒表示
            "file": {"name": tweet.file.name, "type": tweet.file.type, "url": tweet.file.file_url} if tweet.file and tweet.file.file_url else None
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error liking tweet {tweet_id} at {request.url}): {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

@application.route('/api/tweets/<int:tweet_id>/retweet', methods=['POST'])
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
        user_retweeted.add(tweet_id)
        db.session.commit()
        return jsonify({
            "id": tweet.id,
            "username": tweet.username,
            "content": tweet.content,
            "timestamp": tweet.timestamp * 1000,  # 修正: UIでミリ秒表示
            "retweetCount": tweet.retweet_count,
            "goodCount": tweet.good_count,
            "comments": [{"content": comment.content, "timestamp": comment.timestamp * 1000} for comment in tweet.comments],  # 修正: UIでミリ秒表示
            "file": {"name": tweet.file.name, "type": tweet.file.type, "url": tweet.file.file_url} if tweet.file and tweet.file.file_url else None
        })
    except SQLAlchemyError as e:
        logger.exception(f"Error retweeting tweet {tweet_id} at {request.url}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

if __name__ == '__main__':
    application.run(debug=False, host='0.0.0.0', port=8000)  # 修正: debug=False、Gunicorn用にポート指定