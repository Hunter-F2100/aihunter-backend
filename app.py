import os
from flask import Flask, jsonify, request
import requests
from dotenv import load_dotenv
from flask_cors import CORS
import psycopg2
from psycopg2 import extras
from psycopg2 import errorcodes
import bcrypt

# --- 初始化部分 (保持不变) ---
load_dotenv()
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

if not GITHUB_TOKEN or not DATABASE_URL:
    print("错误：GITHUB_TOKEN 或 DATABASE_URL 环境变量未设置！")
    exit(1)

app = Flask(__name__)
CORS(app) 

# --- 数据库和密码函数 (来自您的原始脚本，保持不变) ---
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

# --- 保存候选人函数 (来自您的原始脚本，保持不变) ---
# [建议] 请确保您的 candidates 表中有一个名为 github_id 的列，并且它是 UNIQUE 的，用来做 ON CONFLICT 的判断。
def save_candidate_to_db(candidate_data):
    conn = None
    try:
        conn = get_db_connection()
        if not conn: return False
        cur = conn.cursor()
        insert_sql = """
        INSERT INTO candidates (
            github_id, github_login, name, email, website, company, location, 
            github_url, github_avatar_url, skills
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        values = (
            candidate_data.get('id'), candidate_data.get('login'),
            candidate_data.get('name'), candidate_data.get('email'),
            candidate_data.get('website'), candidate_data.get('company'),
            candidate_data.get('location'), candidate_data.get('githubUrl'),
            candidate_data.get('githubAvatar'), extras.Json(candidate_data.get('skills'))
        )
        cur.execute(insert_sql, values)
        conn.commit()
        cur.close()
        print(f"DEBUG: 候选人 {candidate_data.get('login')} 已成功保存/更新到数据库。")
        return True
    except Exception as e:
        print(f"DEBUG: 保存候选人到数据库失败: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

# --- 您的其他 API (保持不变) ---
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

# ####################################################################
# 警告：下面的 /create-user 和 /login 接口是您原始的登录系统。
# 由于您的前端现在已经切换到 Supabase Auth 进行认证，
# 这两个接口很可能已经不再被调用。
# 我已将它们完整地恢复，但请您知晓，它们可能是“历史遗留代码”。
# ####################################################################

# --- 手动创建用户 API (来自您的原始脚本) ---
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
        if conn: conn.rollback()
        return jsonify(message="创建用户失败，请重试。"), 500
    finally:
        if conn: conn.close()

# --- 用户登录验证 API (来自您的原始脚本) ---
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
        if conn: conn.rollback()
        return jsonify(success=False, message="登录验证失败，请重试。"), 500
    finally:
        if conn: conn.close()


# ####################################################################
# 核心优化：下面的 /search 接口已植入“混合读取”缓存策略
# ####################################################################
@app.route('/search', methods=['GET'])
def search_candidates():
    print("DEBUG: /search 接口收到请求！(已优化)")
    keyword = request.args.get('q', default='')
    page = request.args.get('page', default=1, type=int)
    per_page = 10 

    if not keyword:
        return jsonify(message="请输入搜索关键词"), 400

    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    # === 步骤 1: 从 GitHub 获取基本的用户“名单” ===
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

    # === 步骤 2: 从我们自己的数据库中检查哪些用户已经是“熟人” ===
    user_ids_on_page = [user['id'] for user in github_users_on_page]
    cached_candidates = {}
    conn = get_db_connection()
    if conn:
        try:
            print(f"DEBUG: 步骤2 - 在数据库中查询 {len(user_ids_on_page)} 个用户ID...")
            cur = conn.cursor(cursor_factory=extras.DictCursor)
            # [优化] 使用元组(tuple)作为查询参数，更安全
            cur.execute("SELECT * FROM candidates WHERE github_id = ANY(%s)", (user_ids_on_page,))
            db_results = cur.fetchall()
            cur.close()
            
            for row in db_results:
                cached_candidates[row['github_id']] = dict(row)
            print(f"DEBUG: 缓存命中！在数据库中找到了 {len(cached_candidates)} 个熟人。")
        except Exception as e:
            print(f"DEBUG: 查询数据库缓存时出错: {e}")
        finally:
            if conn: conn.close()

    # === 步骤 3 & 4: 识别“新人”，并只为他们获取详细信息 ===
    final_processed_candidates = []
    
    print("DEBUG: 步骤3&4 - 开始处理用户，优先使用缓存...")
    for user_summary in github_users_on_page:
        user_id = user_summary['id']
        
        if user_id in cached_candidates:
            print(f"DEBUG:  - 用户 {user_summary['login']} (ID: {user_id}) 是熟人，从缓存读取。")
            cached_data = cached_candidates[user_id]
            final_processed_candidates.append({
                "id": cached_data.get("github_id"), "name": cached_data.get("name") or cached_data.get("github_login"),
                "email": cached_data.get("email"), "website": cached_data.get("website"),
                "company": cached_data.get("company"), "skills": cached_data.get("skills", []),
                "location": cached_data.get("location"), "githubUrl": cached_data.get("github_url"),
                "githubAvatar": cached_data.get("github_avatar_url"), "source": "database_cache"
            })
            continue

        try:
            print(f"DEBUG:  - 用户 {user_summary['login']} (ID: {user_id}) 是新人，在线抓取...")
            user_detail_response = requests.get(user_summary['url'], headers=headers)
            user_detail = user_detail_response.json()

            user_repos_response = requests.get(user_detail['repos_url'], headers=headers)
            user_repos = user_repos_response.json()

            skills = [repo['language'] for repo in user_repos if repo.get('language')]
            skills = list(dict.fromkeys(skills))[:5]

            candidate_data = {
                "id": user_detail.get("id"), "login": user_detail.get("login"),
                "name": user_detail.get("name"), "email": user_detail.get("email"),
                "website": user_detail.get("blog"), "company": user_detail.get("company"),
                "location": user_detail.get("location"), "githubUrl": user_detail.get("html_url"),
                "githubAvatar": user_detail.get("avatar_url"), "skills": skills
            }
            
            save_candidate_to_db(candidate_data)
            
            final_processed_candidates.append({
                "id": candidate_data["id"], "name": candidate_data["name"] or candidate_data["login"],
                "email": candidate_data["email"], "website": candidate_data["website"],
                "company": candidate_data["company"], "skills": candidate_data["skills"], 
                "location": candidate_data["location"], "githubUrl": candidate_data["githubUrl"],
                "githubAvatar": candidate_data["githubAvatar"], "source": "github_live"
            })
        except requests.exceptions.RequestException as e:
            print(f"DEBUG: 在线抓取新人 {user_summary['login']} 失败: {e}")
            continue

    # === 步骤 6: 返回合并后的最终结果 ===
    print("DEBUG: 步骤6 - 所有用户处理完毕，返回最终结果。")
    return jsonify({
        "candidates": final_processed_candidates,
        "total_count": github_data.get('total_count', 0),
        "current_page": page,
        "per_page": per_page,
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
