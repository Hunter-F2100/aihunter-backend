import os
from flask import Flask, jsonify, request
import requests
from dotenv import load_dotenv # 引入 load_dotenv 来加载 .env 文件
from flask_cors import CORS # 引入 CORS

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量中获取 GitHub Token
# 如果没有设置环境变量，程序会退出
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    print("错误：GITHUB_TOKEN 环境变量未设置！请在 .env 文件中设置。")
    exit(1) # 如果没有 token，程序退出

# 创建 Flask 应用实例
app = Flask(__name__)
# 允许所有来源的跨域请求，在实际生产环境中应限制为特定的前端域名
CORS(app) 

# --- 您的第一个 '/hello' API 保持不变 ---
@app.route('/hello', methods=['GET'])
def hello_world():
    return jsonify(message='Hello from Flask Backend!')

# --- 搜索 API 接口：调用 GitHub API ---
@app.route('/search', methods=['GET'])
def search_candidates():
    keyword = request.args.get('q', default='')
    page = request.args.get('page', default=1, type=int)
    per_page = 10 # 每页显示10个结果，与前端匹配

    if not keyword:
        return jsonify(candidates=[], total_count=0, current_page=page, per_page=per_page, message="请输入搜索关键词"), 400

    # GitHub 用户搜索 API 接口
    github_api_url = "https://api.github.com/search/users"

    # 请求头，包含认证信息和接受的 API 版本
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json" # 确保使用V3 API
    }

    # 查询参数
    # 搜索用户，根据关键词
    # page: 页码
    # per_page: 每页数量
    params = {
        "q": keyword, # 搜索关键词
        "page": page,
        "per_page": per_page
    }

    try:
        response = requests.get(github_api_url, headers=headers, params=params)
        response.raise_for_status() # 如果请求不成功（如4xx或5xx），则抛出异常

        github_data = response.json()

        processed_candidates = []
        # 遍历 GitHub 返回的用户列表
        for item in github_data.get('items', []):
            # 再次调用 GitHub API 获取每个用户的详细信息，以获取更多字段
            # 注意：这会消耗大量 API 请求，在生产环境中应缓存或优化
            user_detail_response = requests.get(item['url'], headers=headers)
            user_detail_response.raise_for_status()
            user_detail = user_detail_response.json()

            # 模拟获取技术标签，实际需要更复杂的逻辑（如解析 repo 语言）
            # 这里我们从公共仓库的语言中提取前几个作为标签
            user_repos_response = requests.get(user_detail['repos_url'], headers=headers)
            user_repos_response.raise_for_status()
            user_repos = user_repos_response.json()

            skills = []
            for repo in user_repos:
                if repo.get('language') and repo['language'] not in skills:
                    skills.append(repo['language'])
                if len(skills) >= 5: # 最多只获取5个技能
                    break

            processed_candidates.append({
                "id": user_detail.get("id"),
                "name": user_detail.get("name") or user_detail.get("login"), # 优先用name，没有则用login
                "email": user_detail.get("email") or f"{user_detail.get('login')}@example.com", # 优先用email，没有则模拟
                "website": user_detail.get("blog") or user_detail.get("html_url"), # 优先用blog，没有则用github主页
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
        # 处理 HTTP 错误，例如 403 速率限制或 401 认证失败
        print(f"GitHub API 请求失败: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 403:
            return jsonify(message="GitHub API 速率限制，请稍后再试或检查Token。", details=e.response.text), 403
        elif e.response.status_code == 401:
            return jsonify(message="GitHub Token 无效或权限不足。", details=e.response.text), 401
        else:
            return jsonify(message=f"GitHub API 错误: {e.response.status_code}", details=e.response.text), e.response.status_code
    except requests.exceptions.RequestException as e:
        # 处理其他请求错误，如网络连接问题
        print(f"请求异常: {e}")
        return jsonify(message="后端服务请求GitHub API失败。", details=str(e)), 500

# 如果直接运行这个脚本，就启动 Flask 应用
if __name__ == '__main__':
    app.run(debug=True, port=5000)