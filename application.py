# /root/DEATHBILL/application.py
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
import time
import os
import logging
from retrying import retry
import pymysql.err
import uuid
from .urls import blueprints

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
    'connect_args': {'connect_timeout': 10}
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
    file_url = db.Column(db.String(200), nullable=True)

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
                         description="This bill proposes to make all public transportation free for citizens.", timestamp=int(time.time()) - 3600),
                    Bill(id=2, title="Global Education Budget Increase", support=28791, against=1552,
                         description="This bill proposes a 15% increase in the global education budget.", timestamp=int(time.time()) - 1800),
                    Bill(id=3, title="Universal Healthcare Access", support=35762, against=8901,
                         description="A comprehensive plan to provide universal healthcare coverage.", timestamp=int(time.time()) - 7200)
                ]
                db.session.bulk_save_objects(bills)
                logger.info("Inserted initial bills")

            if not Tweet.query.first():
                tweets = [
                    Tweet(id=1, username="👤", content="Politician X proposed a policy to cut public transport funding. Total trash! 🗑️",
                          timestamp=int(time.time()) - 3600, retweet_count=0, good_count=0),
                    Tweet(id=2, username="👤", content="Heard about a new tax break for the ultra-rich? Another garbage policy! 😡",
                          timestamp=int(time.time()) - 1800, retweet_count=0, good_count=0)
                ]
                db.session.bulk_save_objects(tweets)
                tweet_comments = [
                    TweetComment(tweet_id=1, content="That’s awful! We need more funding, not less!", timestamp=int(time.time()) - 3300),
                    TweetComment(tweet_id=1, content="Classic politician move.", timestamp=int(time.time()) - 3000)
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
    from flask import request
    return request.headers.get('X-User-Token', str(uuid.uuid4()))

user_voted_bills = {}
user_liked_comments = {}
user_liked_tweets = {}
user_retweeted_tweets = {}

# Blueprintを登録
for blueprint, prefix in blueprints:
    application.register_blueprint(blueprint, url_prefix=prefix)

if __name__ == '__main__':
    application.run(debug=False, host='0.0.0.0', port=8000)
