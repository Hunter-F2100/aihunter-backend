from dotenv import load_dotenv
import os

load_dotenv()  # 加载.env文件

# 打印确认变量是否加载成功
print("📌 GITHUB_TOKEN:", os.getenv("GITHUB_TOKEN"))
print("📌 DATABASE_URL:", os.getenv("DATABASE_URL"))
print("📌 SUPABASE_SERVICE_KEY:", os.getenv("SUPABASE_SERVICE_KEY"))


import os
import requests
import bcrypt
import psycopg2
import base64
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from flask_cors import CORS
from psycopg2 import extras
from psycopg2 import errorcodes
from datetime import datetime, timedelta, timezone

# --- 初始化部分 ---
load_dotenv()
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

if not GITHUB_TOKEN or not DATABASE_URL:
    print("错误：GITHUB_TOKEN 或 DATABASE_URL 环境变量未设置！")
    exit(1)

app = Flask(__name__)
# [修复] 明确配置 CORS，以允许来自 Next.js 前端 (http://localhost:3000) 的请求
# 这解决了浏览器中的跨域资源共享 (CORS) 策略问题
CORS(app, resources={r"/*": {"origins": ["http://localhost:3000", "https://aihunter.cloud", "http://aihunter.cloud", "https://www.aihunter.cloud"]}})



# --- 数据库和密码函数 (您的原始代码，保持不变) ---
def get_db_connection():
    try:
        if "?sslmode=require" not in DATABASE_URL:
            conn_url = f"{DATABASE_URL}?sslmode=require"
        else:
            conn_url = DATABASE_URL
        conn = psycopg2.connect(conn_url)
        return conn
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return None

def hash_password(password):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def check_password(hashed_password, user_password):
    try:
        return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

# --- 保存候选人函数 (您的原始代码，保持不变) ---
def save_candidate_to_db(conn, candidate_data):
    if not conn:
        print("DEBUG: 无法保存，因为没有可用的数据库连接。")
        return False
    try:
        cur = conn.cursor()
        insert_sql = """
            INSERT INTO candidates (
                github_id, github_login, name, email, website, company, location,
                github_url, github_avatar_url, skills, profile_readme, last_refreshed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (github_id) DO UPDATE SET
                github_login = EXCLUDED.github_login,
                name = EXCLUDED.name,
                email = EXCLUDED.email,
                website = EXCLUDED.website,
                company = EXCLUDED.company,
                location = EXCLUDED.location,
                github_url = EXCLUDED.github_url,
                github_avatar_url = EXCLUDED.github_avatar_url,
                skills = EXCLUDED.skills,
                profile_readme = EXCLUDED.profile_readme,
                last_refreshed_at = EXCLUDED.last_refreshed_at;
        """
        values = (
            candidate_data.get('id'),
            candidate_data.get('login'),
            candidate_data.get('name'),
            candidate_data.get('email'),
            candidate_data.get('website'),
            candidate_data.get('company'),
            candidate_data.get('location'),
            candidate_data.get('githubUrl'),
            candidate_data.get('githubAvatar'),
            extras.Json(candidate_data.get('skills')),
            candidate_data.get('profile_readme'),
            candidate_data.get('last_refreshed_at')
        )
        cur.execute(insert_sql, values)
        cur.close()
        print(f"DEBUG: 候选人 {candidate_data.get('login')} 的数据已准备好保存/更新。")
        return True
    except Exception as e:
        print(f"DEBUG: 准备保存候选人数据时失败: {e}")
        return False

# --- 您的其他 API (您的原始代码，保持不变) ---
@app.route('/hello', methods=['GET'])
def hello_world():
    return jsonify(message='Hello from Flask Backend!')

@app.route('/test-db', methods=['GET'])
def test_db_connection():
    conn = get_db_connection()
    if conn:
        conn.close()
        return jsonify(message="数据库连接成功！"), 200
    else:
        return jsonify(message="数据库连接失败。"), 500

# --- 手动创建用户 API (您的原始代码，保持不变) ---
@app.route('/create-user', methods=['POST'])
def create_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify(message="用户名和密码不能为空。"), 400
    hashed_password = hash_password(password)
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify(message="数据库连接失败，无法创建用户。"), 500
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            return jsonify(message="用户名已存在，请选择其他用户名。"), 409
        insert_sql = "INSERT INTO users (username, password_hash) VALUES (%s, %s);"
        cur.execute(insert_sql, (username, hashed_password))
        conn.commit()
        cur.close()
        return jsonify(message=f"用户 '{username}' 创建成功！"), 201
    except Exception as e:
        print(f"创建用户失败: {e}")
        if conn:
            conn.rollback()
        return jsonify(message="创建用户失败，请重试。"), 500
    finally:
        if conn:
            conn.close()

# --- 用户登录验证 API (您的原始代码，保持不变) ---
@app.route('/login', methods=['POST'])
def login_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify(success=False, message="用户名和密码不能为空。"), 400
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify(success=False, message="数据库连接失败，无法验证用户。"), 500
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash, email FROM users WHERE username = %s", (username,))
        user_record = cur.fetchone()
        cur.close()
        if user_record:
            db_user_id, db_username, db_password_hash, db_email = user_record
            if check_password(db_password_hash, password):
                return jsonify(
                    success=True,
                    user={"id": str(db_user_id), "username": db_username, "email": db_email},
                    message="登录成功。"
                ), 200
            else:
                return jsonify(success=False, message="用户名或密码不正确。"), 401
        else:
            return jsonify(success=False, message="用户名或密码不正确。"), 401
    except Exception as e:
        print(f"登录验证失败: {e}")
        if conn:
            conn.rollback()
        return jsonify(success=False, message="登录验证失败，请重试。"), 500
    finally:
        if conn:
            conn.close()

# --- 核心搜索 API (您的原始业务逻辑，保持不变) ---
@app.route('/search', methods=['GET'])
def search_candidates():
    print("DEBUG: /search 接口收到请求！(最终智能版)")
    keyword = request.args.get('q', default='')
    page = request.args.get('page', default=1, type=int)
    per_page = 10

    if not keyword:
        return jsonify(message="请输入搜索关键词"), 400

    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    # 步骤 1: 获取 GitHub 用户名单
    try:
        print(f"DEBUG: 步骤1 - 从 GitHub 获取第 {page} 页的用户名单...")
        search_params = {"q": keyword, "page": page, "per_page": per_page}
        response = requests.get("https://api.github.com/search/users", headers=headers, params=search_params)
        response.raise_for_status()
        github_data = response.json()
        github_users_on_page = github_data.get('items', [])
        if not github_users_on_page:
            print("DEBUG: GitHub 未返回任何用户。")
            return jsonify(candidates=[], total_count=0)
    except requests.exceptions.RequestException as e:
        print(f"GitHub API 请求失败: {e}")
        return jsonify(message="GitHub API 请求失败。", details=str(e)), 500

    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            print("警告: 数据库连接失败，将仅依赖在线抓取。")

        # 步骤 2: 核对数据库缓存
        user_ids_on_page = [user['id'] for user in github_users_on_page]
        cached_candidates = {}
        if conn:
            try:
                cur = conn.cursor(cursor_factory=extras.DictCursor)
                cur.execute("SELECT * FROM candidates WHERE github_id = ANY(%s)", (user_ids_on_page,))
                db_results = cur.fetchall()
                cur.close()
                for row in db_results:
                    cached_candidates[row['github_id']] = dict(row)
                print(f"DEBUG: 缓存命中！在数据库中找到了 {len(cached_candidates)} 个熟人。")
            except Exception as e:
                print(f"DEBUG: 查询数据库缓存时出错: {e}")

        # 步骤 3: 循环处理每个用户
        final_processed_candidates = []
        for user_summary in github_users_on_page:
            user_id = user_summary['id']
            cached_data = cached_candidates.get(user_id)
            should_fetch_online = True
            
            if cached_data:
                is_stale = False
                last_refresh = cached_data.get('last_refreshed_at')
                if not last_refresh or (datetime.now(timezone.utc) - last_refresh > timedelta(days=30)):
                    is_stale = True
                    print(f"DEBUG: - 熟人 {user_summary['login']} 的数据已过期，需要强制刷新。")
                
                needs_readme_update = not cached_data.get("profile_readme")
                if needs_readme_update:
                    print(f"DEBUG: - 熟人 {user_summary['login']} 的档案不完整，需要补充个人简介。")
                
                if not is_stale and not needs_readme_update:
                    should_fetch_online = False
            
            if not should_fetch_online:
                print(f"DEBUG: - 用户 {user_summary['login']} 是完美的熟人，从缓存读取。")
                
                ### ===============================================================================
                ### ===                           【关键修复】                                    ===
                ### === 以下代码块是唯一被修改的地方。它将数据库返回的缓存数据进行“标准化”，   ===
                ### === 确保返回给前端的字段名 (key) 永远和实时抓取的数据一致。               ===
                ### ===============================================================================
                normalized_cache = {
                    **cached_data,
                    "githubAvatar": cached_data.get("github_avatar_url"), # <-- 关键修复：添加前端期望的字段
                    "githubUrl": cached_data.get("github_url"),         # <-- 顺便也统一一下 GitHub 主页地址的字段
                    "source": "database_cache"
                }
                final_processed_candidates.append(normalized_cache)
                continue

            # 在线抓取或更新
            try:
                print(f"DEBUG: - 在线抓取/更新用户 {user_summary['login']} 的完整信息...")
                user_detail_response = requests.get(user_summary['url'], headers=headers)
                user_detail_response.raise_for_status()
                user_detail = user_detail_response.json()

                user_repos_response = requests.get(user_detail['repos_url'], headers=headers)
                user_repos_response.raise_for_status()
                user_repos = user_repos_response.json()
                skills = list(dict.fromkeys([repo['language'] for repo in user_repos if repo.get('language')]))[:5]
                
                profile_readme_content = None
                try:
                    readme_url = f"https://api.github.com/repos/{user_summary['login']}/{user_summary['login']}/readme"
                    readme_response = requests.get(readme_url, headers=headers)
                    if readme_response.status_code == 200:
                        profile_readme_content = base64.b64decode(readme_response.json().get('content', '')).decode('utf-8')
                except Exception:
                    pass
                
                candidate_full_data = {
                    "id": user_detail.get("id"),
                    "github_id": user_detail.get("id"),
                    "login": user_detail.get("login"),
                    "name": user_detail.get("name"),
                    "email": user_detail.get("email"),
                    "website": user_detail.get("blog"),
                    "company": user_detail.get("company"),
                    "location": user_detail.get("location"),
                    "githubUrl": user_detail.get("html_url"),
                    "githubAvatar": user_detail.get("avatar_url"),
                    "skills": skills,
                    "profile_readme": profile_readme_content,
                    "last_refreshed_at": datetime.now(timezone.utc)
                }
                
                if conn:
                    save_candidate_to_db(conn, candidate_full_data)
                
                candidate_full_data["source"] = "github_live_refresh"
                final_processed_candidates.append(candidate_full_data)

            except requests.exceptions.RequestException as e:
                print(f"DEBUG: 在线抓取/更新 {user_summary['login']} 失败: {e}")
                if cached_data:
                    cached_data["source"] = "database_cache_stale"
                    final_processed_candidates.append(cached_data)
                continue
        
        if conn:
            conn.commit()
            print("DEBUG: 数据库事务已成功提交。")
            
        return jsonify({
            "candidates": final_processed_candidates,
            "total_count": github_data.get('total_count', 0),
            "current_page": page,
            "per_page": per_page,
        })

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify(message=f"处理搜索时发生未知错误: {e}"), 500
    finally:
        if conn:
            conn.close()
            print("DEBUG: 数据库连接已关闭。")

if __name__ == '__main__':
    # [修复] 将主机绑定到 '0.0.0.0' 以解决 403 Forbidden 错误。
    # 这使得服务器可以从外部网络接口（包括本地主机上的其他服务，如 Next.js）接收请求。
    # 默认的 '127.0.0.1' 绑定过于严格，是导致问题的主要原因。
    app.run(host='0.0.0.0', port=5001, debug=True)