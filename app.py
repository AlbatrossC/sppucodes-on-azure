from flask import Flask, render_template, send_from_directory, abort, request, redirect, url_for, flash, jsonify, current_app
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError
from dotenv import load_dotenv
import os
import psycopg2
import json
from functools import lru_cache
from datetime import datetime

# ------------------- App Configuration -------------------
app = Flask(__name__)
app.secret_key = 'karlos'

# Directory paths
BASE_DIR = os.path.join(os.path.dirname(__file__), 'static', 'pyqs')
DOWNLOADS_FOLDER = os.path.join(app.root_path, 'downloads')
IMAGES_DIR = os.path.join(os.path.dirname(__file__), 'images')
QUESTIONS_DIR = os.path.join(os.path.dirname(__file__), 'questions')

# Cache settings
CACHE_TIMEOUT = 3600  # Cache timeout in seconds

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')

# ------------------- Database Utilities -------------------
def connect_db():
    """Connect to PostgreSQL database."""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

# ------------------- Azure Blob Storage Utilities -------------------
def get_blob_container_client(container_name):
    """Initialize and return the Azure Blob container client with error handling."""
    try:
        if not AZURE_STORAGE_CONNECTION_STRING:
            raise ValueError("Azure Storage connection string not found in environment variables")
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        return blob_service_client.get_container_client(container_name)
    except Exception as e:
        current_app.logger.error(f"Failed to initialize Azure Blob Storage client: {str(e)}")
        raise

# ------------------- File and Directory Utilities -------------------
@lru_cache(maxsize=1024)
def _get_directory_contents(full_path):
    """Get directory contents (cached)."""
    try:
        items = os.listdir(full_path)
        if any(item.lower().endswith('.pdf') for item in items):
            return [f for f in items if f.lower().endswith('.pdf')]
        return [d for d in items if os.path.isdir(os.path.join(full_path, d))]
    except Exception as e:
        print(f"Error reading directory {full_path}: {e}")
        return []

# ------------------- Routes: Static File Serving -------------------
@app.route('/static/pyqs/<path:filename>')
def serve_pdf(filename):
    """Serve static PDFs with caching headers."""
    response = send_from_directory(BASE_DIR, filename, max_age=CACHE_TIMEOUT)
    response.headers['Cache-Control'] = f'public, max-age={CACHE_TIMEOUT}'
    return response

@app.route('/downloads/<filename>')
def download_file(filename):
    """Serve files from downloads folder."""
    return send_from_directory(DOWNLOADS_FOLDER, filename)

@app.route('/images/<filename>')
def get_image(filename):
    """Serve image files."""
    return send_from_directory(IMAGES_DIR, filename)

@app.route('/sitemap.xml')
def sitemap():
    """Serve sitemap.xml."""
    return send_from_directory('.', 'sitemap.xml')

@app.route('/robots.txt')
def robots():
    """Serve robots.txt."""
    return send_from_directory('.', 'robots.txt')

# ------------------- Routes: Form Handling -------------------
@app.route('/submit', methods=["GET", "POST"])
def submit():
    """Handle form submission for questions and answers."""
    conn = connect_db()
    if conn is None:
        return "Database Connection error. Please try again later"

    if request.method == "POST":
        try:
            cur = conn.cursor()
            name = request.form.get("name")
            year = request.form.get("year")
            branch = request.form.get("branch")
            subject = request.form.get("subject")
            question = request.form.get("question")
            answer = request.form.get("answer")

            if all([name, year, branch, subject, question, answer]):
                cur.execute(
                    "INSERT INTO codes (name, year, branch, subject, question, answer) VALUES (%s,%s,%s,%s,%s,%s)",
                    (name, year, branch, subject, question, answer)
                )
                conn.commit()
                flash("Code Sent Successfully! Thank you", "success")
                return redirect(url_for('submit'))
            else:
                flash("PLEASE FILL ALL NECESSARY FIELDS", "error")
        except Exception as e:
            flash(f"Error inserting data: {e}", "error")
        finally:
            cur.close()
            conn.close()
    return render_template("submit.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    """Handle contact form submission."""
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        if all([name, email, message]):
            try:
                conn = connect_db()
                if conn is None:
                    flash("Database connection error. Please try again later.", "error")
                    return redirect(url_for('contact'))

                cur = conn.cursor()
                cur.execute("INSERT INTO contacts (name, email, message) VALUES (%s, %s, %s)",
                            (name, email, message))
                conn.commit()
                flash("Message sent successfully! Thank you", "success")
            except Exception as e:
                flash(f"Error inserting data: {e}", "error")
            finally:
                if 'cur' in locals():
                    cur.close()
                if 'conn' in locals():
                    conn.close()
            return redirect(url_for('contact'))
        else:
            flash("PLEASE FILL ALL NECESSARY FIELDS", "error")
    return render_template("contact.html")

# ------------------- Routes: Question Papers and Viewer -------------------
@app.route('/questionpapers')
def select():
    """Render question paper selection page."""
    return render_template('select.html')

@app.route('/api/directories')
def get_directories():
    """API to fetch list of directories or PDF files."""
    path = request.args.get('path', '')
    if path.startswith('pyqs/'):
        path = path[len('pyqs/'):]
    full_path = os.path.join(BASE_DIR, path)
    if not os.path.exists(full_path):
        return jsonify([])
    if os.path.isdir(full_path):
        return jsonify(_get_directory_contents(full_path))
    return jsonify([])

@app.route('/viewer')
def viewer():
    """Render PDF viewer page."""
    pdf_path = request.args.get('pdf')
    return render_template('viewer.html', pdf_path=pdf_path)

# ------------------- Routes: Subject and Questions -------------------
@app.route("/<subject_code>")
@app.route("/<subject_code>/<question_id>")
def question(subject_code, question_id=None):
    """Serve questions and answers by subject code."""
    try:
        # Load JSON from Azure Blob in 'questions' container
        questions_container = get_blob_container_client("questions")
        blob_client = questions_container.get_blob_client(f"{subject_code}.json")
        json_content = blob_client.download_blob().readall().decode('utf-8')
        data = json.loads(json_content)
    except AzureError as e:
        current_app.logger.error(f"Error loading questions JSON from Azure: {str(e)}")
        abort(404, description="Subject not found")

    subject = data.get("default", {})
    questions = data.get("questions", [])
    question_dict = {q["id"]: q for q in questions}

    title = f"SPPU Codes - {subject.get('subject_name', '')}"
    description = subject.get("description", "")
    keywords = subject.get("keywords", [])
    url = subject.get("url", f"https://sppucodes.vercel.app/{subject_code}")

    selected_question = question_dict.get(question_id) if question_id else None
    if selected_question:
        title = selected_question["question"]
        description = f"SPPU Codes: {selected_question['question']}"
        keywords = [selected_question["question"], selected_question["title"]] + subject.get("keywords", [])
        url = f"https://sppucodes.vercel.app/{subject_code}/{question_id}"

    # Grouping questions
    groups = {}
    for q in questions:
        groups.setdefault(q["group"], []).append(q)

    # Load answer files from 'answers' container
    file_contents = {}
    try:
        answers_container = get_blob_container_client("answers")
        for q in questions:
            if isinstance(q.get("file_name"), list):
                file_contents[q["id"]] = {}
                for filename in q["file_name"]:
                    blob_path = f"{subject_code}/{filename}"
                    try:
                        blob_client = answers_container.get_blob_client(blob_path)
                        stream = blob_client.download_blob()
                        content = stream.readall().decode('utf-8')
                        file_contents[q["id"]][filename] = content
                    except AzureError as e:
                        current_app.logger.error(f"Error loading {blob_path}: {str(e)}")
                        file_contents[q["id"]][filename] = "Error loading file content"
            elif q.get("file_name"):
                filename = q["file_name"]
                blob_path = f"{subject_code}/{filename}"
                try:
                    blob_client = answers_container.get_blob_client(blob_path)
                    stream = blob_client.download_blob()
                    content = stream.readall().decode('utf-8')
                    file_contents[q["id"]] = {filename: content}
                except AzureError as e:
                    current_app.logger.error(f"Error loading {blob_path}: {str(e)}")
                    file_contents[q["id"]] = {filename: "Error loading file content"}
    except Exception as e:
        current_app.logger.error(f"Azure Blob Storage error (answers): {str(e)}")
        file_contents = {
            q["id"]: {
                f: "Service unavailable"
                for f in (q["file_name"] if isinstance(q.get("file_name"), list) else [q["file_name"]])
            }
            for q in questions if q.get("file_name")
        }

    return render_template(
        "subject.html",
        title=title,
        description=description,
        keywords=keywords,
        url=url,
        subject_code=subject_code,
        subject_name=subject.get("subject_name", ""),
        groups=groups,
        sorted_groups=sorted(groups.keys()),
        question=selected_question,
        file_contents=file_contents
    )

# ------------------- Routes: Home and Downloads -------------------
@app.route('/')
def index():
    """Render home page."""
    return render_template('index.html')

@app.route('/download')
def download():
    """Render downloads page."""
    return render_template('download.html')

# ------------------- Commented-Out Routes -------------------
# @app.route('/answers/<subject>/<filename>')
# def get_answer(subject, filename):
#     try:
#         base_dir = os.path.abspath(os.path.dirname(__file__))
#         answers_dir = os.path.join(base_dir, 'answers', subject)
#         full_path = os.path.join(answers_dir, filename)
#         if not os.path.exists(answers_dir) or not os.path.exists(full_path):
#             abort(404)
#         return send_from_directory(answers_dir, filename)
#     except Exception:
#         abort(404)

# @app.route('/answers/<subject>/<filename>')
# def get_answer(subject, filename):
#     try:
#         base_url = "https://sppucodes.blob.core.windows.net/answers"
#         blob_url = f"{base_url}/{subject}/{filename}"
#         return redirect(blob_url)
#     except Exception:
#         abort(404)

# ------------------- Error Handlers -------------------
@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    return render_template('error.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 errors."""
    return render_template('error.html'), 500

# ------------------- Response Middleware -------------------
@app.after_request
def inject_clarity(response):
    """Inject Microsoft Clarity script into HTML responses."""
    if response.content_type.startswith('text/html'):
        clarity_script = """
        <script>
        (function(c,l,a,r,i,t,y){
            c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
            t=l.createElement(r);
            t.async=1;
            t.src="https://www.clarity.ms/tag/"+i;
            y=l.getElementsByTagName("head")[0] || l.getElementsByTagName(r)[0];
            y.parentNode.insertBefore(t,y);
        })(window, document, "clarity", "script", "qnqi8o9y94");
        </script>
        """
        response.direct_passthrough = False
        response.set_data(response.get_data().replace(
            b'</body>', clarity_script.encode('utf-8') + b'</body>'
        ))
    return response

# ------------------- Main Application Runner -------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)