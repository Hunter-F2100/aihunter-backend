import os
from flask import Flask, jsonify, request
import requests
from dotenv import load_dotenv
from flask_cors import CORS
import psycopg2
from psycopg2 import extras
from psycopg2 import errorcodes
import bcrypt

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量中获取 GitHub Token
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    print("错误：GITHUB_TOKEN 环境变量未设置！请在 .env 文件中设置。")
    exit(1)

# 从环境变量中获取数据库连接 URL 和 Supabase Service Key
DATABASE_URL = os.getenv('DATABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
if not DATABASE_URL or not SUPABASE_SERVICE_KEY:
    print("错误：DATABASE_URL 或 SUPABASE_SERVICE_KEY 环境变量未设置！请在 .env 文件中设置。")
    exit(1)

# 创建 Flask 应用实例
app = Flask(__name__)
CORS(app) 

# --- 数据库连接函数 ---
def get_db_connection():
    try:
        if "?sslmode=require" not in DATABASE_URL:
            print("警告：DATABASE_URL 未包含 sslmode=require，尝试添加。")
            conn_url = f"{DATABASE_URL}?sslmode=require"
        else:
            conn_url = DATABASE_URL

        conn = psycopg2.connect(conn_url)
        print("DEBUG: 数据库连接成功创建！")
        return conn
    except Exception as e:
        print(f"DEBUG: 数据库连接失败: {e}")
        return None

# --- 密码加密与验证函数 ---
def hash_password(password):
    """对密码进行哈希加密"""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8') # 返回字符串形式

def check_password(hashed_password, user_password):
    """验证密码是否与哈希值匹配"""
    try:
        return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        # 如果 hashed_password 格式不正确，例如不是有效的bcrypt哈希，会抛出ValueError
        return False

# --- 保存候选人到数据库的函数 ---
def save_candidate_to_db(candidate_data):
    print(f"DEBUG: 尝试保存候选人到数据库: {candidate_data.get('login')}")
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            print("DEBUG: 错误：无法保存候选人，因为数据库连接失败。")
            return False

        cur = conn.cursor()

        insert_sql = """
        INSERT INTO candidates (
            github_id, github_login, name, email, website, company, location, 
            github_url, github_avatar_url, skills
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
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
            created_at = NOW(); 
        """

        github_id_val = candidate_data.get('id')
        github_login_val = candidate_data.get('login')

        if github_id_val is None or github_login_val is None:
            print(f"DEBUG: 警告：无法保存候选人到数据库，因为 github_id ({github_id_val}) 或 github_login ({github_login_val}) 为空。")
            return False

        values = (
            github_id_val, 
            github_login_val,
            candidate_data.get('name'),
            candidate_data.get('email'),
            candidate_data.get('website'),
            candidate_data.get('company'),
            candidate_data.get('location'),
            candidate_data.get('githubUrl'),
            candidate_data.get('githubAvatar'),
            extras.Json(candidate_data.get('skills'))
        )

        print("DEBUG: --- 尝试插入/更新数据库 ---")
        cur.execute(insert_sql, values)
        conn.commit()
        cur.close()
        print(f"DEBUG: 候选人 {candidate_data.get('login')} 已成功保存/更新到数据库。")
        return True
    except psycopg2.Error as e: 
        conn.rollback()
        print(f"DEBUG: 保存候选人到数据库失败: PostgreSQL Error {e.pgcode} - {e.pgerror.strip()}")
        if e.pgcode == errorcodes.UNIQUE_VIOLATION:
            print(f"DEBUG: 可能是重复的候选人：{candidate_data.get('login')} (GitHub ID: {candidate_data.get('id')})")
        return False
    except Exception as e:
        print(f"DEBUG: 保存候选人到数据库失败: 通用错误 - {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# --- 您的 '/hello' API 保持不变 ---
@app.route('/hello', methods=['GET'])
def hello_world():
    return jsonify(message='Hello from Flask Backend!')

# --- 测试数据库连接的 API ---
@app.route('/test-db', methods=['GET'])
def test_db_connection():
    conn = get_db_connection()
    if conn:
        conn.close()
        return jsonify(message="数据库连接成功！"), 200
    else:
        return jsonify(message="数据库连接失败，请检查配置和网络。"), 500

# --- 手动创建用户 API (所有者使用) ---
@app.route('/create-user', methods=['POST'])
def create_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify(message="用户名和密码不能为空。"), 400

    hashed_password = hash_password(password) # 加密密码

    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify(message="数据库连接失败，无法创建用户。"), 500

        cur = conn.cursor()
        # 检查用户名是否已存在
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            return jsonify(message="用户名已存在，请选择其他用户名。"), 409 # 409 Conflict

        # 插入新用户
        insert_sql = """
        INSERT INTO users (username, password_hash)
        VALUES (%s, %s);
        """
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

# --- 新增：用户登录验证 API (供 NextAuth.js 调用) ---
@app.route('/login', methods=['POST'])
def login_user():
    print("DEBUG: /login 接口收到请求！")
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
        # 根据用户名查询用户
        cur.execute("SELECT id, username, password_hash, email FROM users WHERE username = %s", (username,))
        user_record = cur.fetchone()
        cur.close()

        if user_record:
            # 假设 user_record 结构是 (id, username, password_hash, email)
            db_user_id, db_username, db_password_hash, db_email = user_record

            # 验证密码
            if check_password(db_password_hash, password):
                # 密码正确，返回成功信息和用户基本信息
                return jsonify(
                    success=True,
                    user={
                        "id": str(db_user_id), # UUID 转字符串
                        "username": db_username,
                        "email": db_email # NextAuth.js session 会使用 email
                    },
                    message="登录成功。"
                ), 200
            else:
                # 密码不正确
                return jsonify(success=False, message="用户名或密码不正确。"), 401 # 401 Unauthorized
        else:
            # 用户名不存在
            return jsonify(success=False, message="用户名或密码不正确。"), 401
    except Exception as e:
        print(f"登录验证失败: {e}")
        if conn:
            conn.rollback()
        return jsonify(success=False, message="登录验证失败，请重试。"), 500
    finally:
        if conn:
            conn.close()

# --- 搜索 API 接口：调用 GitHub API 并保存数据 ---
@app.route('/search', methods=['GET'])
def search_candidates():
    print("DEBUG: /search 接口收到请求！")
    keyword = request.args.get('q', default='')
    page = request.args.get('page', default=1, type=int)
    per_page = 10 

    if not keyword:
        return jsonify(candidates=[], total_count=0, current_page=page, per_page=per_page, message="请输入搜索关键词"), 400

    github_api_url = "https://api.github.com/search/users"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.com.v3+json"
    }

    params = {
        "q": keyword,
        "page": page,
        "per_page": per_page
    }

    try:
        response = requests.get(github_api_url, headers=headers, params=params)
        response.raise_for_status() 

        github_data = response.json()

        processed_candidates = []
        print(f"DEBUG: 从 GitHub 收到 {len(github_data.get('items', []))} 个项目。")
        for item in github_data.get('items', []):
            user_detail_response = requests.get(item['url'], headers=headers)
            user_detail_response.raise_for_status()
            user_detail = user_detail_response.json()

            user_repos_response = requests.get(user_detail['repos_url'], headers=headers)
            user_repos_response.raise_for_status()
            user_repos = user_repos_response.json()

            skills = []
            for repo in user_repos:
                if repo.get('language') and repo['language'] not in skills:
                    skills.append(repo['language'])
                if len(skills) >= 5:
                    break

            candidate_for_db = {
                "id": user_detail.get("id"),
                "login": user_detail.get("login"),
                "name": user_detail.get("name"),
                "email": user_detail.get("email"),
                "website": user_detail.get("blog"),
                "company": user_detail.get("company"),
                "location": user_detail.get("location"),
                "githubUrl": user_detail.get("html_url"),
                "githubAvatar": user_detail.get("avatar_url"),
                "skills": skills,
            }

            save_candidate_to_db(candidate_for_db)

            processed_candidates.append({
                "id": user_detail.get("id"),
                "name": user_detail.get("name") or user_detail.get("login"),
                "email": user_detail.get("email") or f"{user_detail.get('login')}@example.com",
                "website": user_detail.get("blog") or user_detail.get("html_url"),
                "company": user_detail.get("company", "N/A"),
                "skills": skills, 
                "location": user_detail.get("location", "N/A"),
                "githubUrl": user_detail.get("html_url"),
                "githubAvatar": user_detail.get("avatar_url"),
            })

        return jsonify({
            "candidates": processed_candidates,
            "total_count": github_data.get('total_count', 0),
            "current_page": page,
            "per_page": per_page,
            "message": "搜索成功"
        })

    except requests.exceptions.HTTPError as e:
        print(f"GitHub API 请求失败: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 403:
            return jsonify(message="GitHub API 速率限制，请稍后再试或检查Token。", details=e.response.text), 403
        elif e.response.status_code == 401:
            return jsonify(message="GitHub Token 无效或权限不足。", details=e.response.text), 401
        else:
            return jsonify(message=f"GitHub API 错误: {e.response.status_code}", details=e.response.text), e.response.status_code
    except requests.exceptions.RequestException as e:
        print(f"请求异常: {e}")
        return jsonify(message="后端服务请求GitHub API失败。", details=str(e)), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)