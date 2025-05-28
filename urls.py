from flask import Blueprint, jsonify
from urllib.parse import urlencode

# 仮の関数を追加
def uri_to_iri(uri):
    return uri  # 今はそのまま返すだけでOK

def _urlencode(params):
    # params は dict だと仮定
    return urlencode(params)

# 各Blueprintを定義
api_bp = Blueprint('api', __name__, url_prefix='/api')
main_bp = Blueprint('main', __name__)

# メインルートのエンドポイント
@main_bp.route('/')
def home():
    return jsonify({"message": "Welcome to DEATHBILL API!"})

# APIエンドポイントの例
@api_bp.route('/status', methods=['GET'])
def status():
    return jsonify({"status": "API is running", "version": "1.0.0"})

@api_bp.route('/test', methods=['GET'])
def test():
    return jsonify({"test": "This is a test endpoint"})

# Blueprintをリストとしてまとめる
blueprints = [
    (main_bp, ''),
    (api_bp, '/api')
]
