from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from flask_session import Session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from chat import get_response, PROMPTS
import json
import logging
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import csv
from io import StringIO
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from flask_cors import CORS

# Define the folder containing HTML files


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}) # Allow requests from Node.js server

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Replace with a secure key
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(app.instance_path, 'sessions')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chats.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
Session(app)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Email configuration (replace with your SMTP settings)
EMAIL_CONFIG = {
    'SMTP_SERVER': 'smtp.gmail.com',
    'SMTP_PORT': 587,
    'SENDER_EMAIL': 'your-email@gmail.com',
    'SENDER_PASSWORD': 'your-app-password',
    'FALLBACK_EMAIL': 'fallback-support@example.com'
}

# Setup logging
logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

try:
    with open('intents.json', 'r', encoding='utf-8') as json_data:
        intents = json.load(json_data)
except Exception as e:
    logging.error(f"Failed to load intents.json: {e}")
    raise

# Database Models
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), nullable=False)
    language = db.Column(db.String(20))
    sender = db.Column(db.String(10))  # 'user' or 'bot'
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class SupportRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), nullable=False)
    language = db.Column(db.String(20))
    department = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    civil_id = db.Column(db.String(20), nullable=False)
    contact_number = db.Column(db.String(50), nullable=False)
    university = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class AdminUser(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(AdminUser, int(user_id))

def send_support_email(support_data, language):
    try:
        department_emails = {
            'Admissions': intents['intents']['English']['tags']['Support']['departments']['Admissions']['email'],
            'Finance': intents['intents']['English']['tags']['Support']['departments']['Finance']['email'],
            'IT Support': intents['intents']['English']['tags']['Support']['departments']['IT Support']['email'],
            'General Inquiries': intents['intents']['English']['tags']['Support']['departments']['General Inquiries']['email'],
            'القبول': intents['intents']['Arabic']['tags']['الدعم']['departments']['القبول']['email'],
            'الشؤون المالية': intents['intents']['Arabic']['tags']['الدعم']['departments']['الشؤون المالية']['email'],
            'دعم تقنية المعلومات': intents['intents']['Arabic']['tags']['الدعم']['departments']['دعم تقنية المعلومات']['email'],
            'الاستفسارات العامة': intents['intents']['Arabic']['tags']['الدعم']['departments']['الاستفسارات العامة']['email']
        }
        recipient_email = department_emails.get(support_data['department'], EMAIL_CONFIG['FALLBACK_EMAIL'])
        logging.debug(f"Attempting to send email to: {recipient_email} for department: {support_data['department']}")

        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['SENDER_EMAIL']
        msg['To'] = recipient_email
        msg['Subject'] = f"Support Request - {support_data['department']}"

        body = f"""
New Support Request
Language: {language}
Department: {support_data['department']}
Name: {support_data['name']}
Civil ID: {support_data['civil_id']}
Contact Number: {support_data['contact_number']}
University: {support_data['university'] or 'Not provided'}
Subject/Message: {support_data['message']}
Session ID: {support_data['session_id']}
Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}
"""
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(EMAIL_CONFIG['SMTP_SERVER'], EMAIL_CONFIG['SMTP_PORT']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['SENDER_EMAIL'], EMAIL_CONFIG['SENDER_PASSWORD'])
            server.send_message(msg)
        logging.info(f"Support email sent to {recipient_email} for session {support_data['session_id']}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"SMTP authentication failed for {EMAIL_CONFIG['SENDER_EMAIL']}: {str(e)}")
        return False
    except smtplib.SMTPException as e:
        logging.error(f"SMTP error sending email to {recipient_email}: {str(e)}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error sending email to {recipient_email}: {str(e)}")
        return False

@app.get('/')
def index_get():
    try:
        session['chat_state'] = {
            'state': 'language',
            'selected_language': None,
            'selected_tag': None,
            'user_name': None,
            'civil_id': None,
            'support_data': None
        }
        logging.debug("Initialized session state")
        return render_template('index.html')
    except Exception as e:
        logging.error(f"Error in index_get: {e}")
        return jsonify({'error': 'Server error initializing session'}), 500

@app.post('/predict')
def predict():
    try:
        data = request.get_json()
        text = data.get('message')
        logging.debug(f"Received message: {text}")
        if not text:
            logging.error("No message provided")
            return jsonify({'error': 'No message provided'}), 400
        if text == "get_state":
            state = session.get('chat_state', {
                'state': 'language',
                'selected_language': None,
                'selected_tag': None,
                'user_name': None,
                'civil_id': None,
                'support_data': None
            })
            logging.debug(f"Returning state: {state}")
            return jsonify({'state': state['state']})
        
        state = session.get('chat_state', {
            'state': 'language',
            'selected_language': None,
            'selected_tag': None,
            'user_name': None,
            'civil_id': None,
            'support_data': None
        })
        response, new_state = get_response(text, state)
        session['chat_state'] = new_state
        if text != "RESTART":
            chat = ChatMessage(
                session_id=session.sid,
                language=state.get('selected_language', 'Unknown'),
                sender='user',
                message=text
            )
            db.session.add(chat)
            if response and response != "RESTART":
                if isinstance(response, list):
                    for msg in response:
                        bot_chat = ChatMessage(
                            session_id=session.sid,
                            language=state.get('selected_language', 'Unknown'),
                            sender='bot',
                            message=msg
                        )
                        db.session.add(bot_chat)
                        logging.debug(f"Saved bot message: {msg}")
                else:
                    bot_chat = ChatMessage(
                        session_id=session.sid,
                        language=state.get('selected_language', 'Unknown'),
                        sender='bot',
                        message=response
                    )
                    db.session.add(bot_chat)
                    logging.debug(f"Saved bot message: {response}")
            db.session.commit()
        
        if new_state.get('support_data') and new_state['state'] == 'support_complete':
            support_request = SupportRequest(
                session_id=session.sid,
                language=state.get('selected_language', 'Unknown'),
                department=new_state['support_data']['department'],
                name=new_state['support_data']['name'],
                civil_id=new_state['support_data']['civil_id'],
                contact_number=new_state['support_data']['contact_number'],
                university=new_state['support_data']['university'],
                message=new_state['support_data']['message']
            )
            db.session.add(support_request)
            db.session.commit()
            email_sent = send_support_email({
                'department': new_state['support_data']['department'],
                'name': new_state['support_data']['name'],
                'civil_id': new_state['support_data']['civil_id'],
                'contact_number': new_state['support_data']['contact_number'],
                'university': new_state['support_data']['university'],
                'message': new_state['support_data']['message'],
                'session_id': session.sid
            }, state['selected_language'])
            if not email_sent:
                logging.error("Email sending failed, but support request saved to database")
                response = PROMPTS[state['selected_language']]['support_complete'] + " (Note: Email sending failed, please contact support)"
            new_state['support_data'] = None
            session['chat_state'] = new_state
        logging.debug(f"Response: {response}, New state: {new_state}")
        if response == "RESTART":
            return jsonify({'answer': '', 'restart': True})
        if isinstance(response, list):
            return jsonify({'answers': response})
        return jsonify({'answer': response})
    except Exception as e:
        logging.error(f"Error in predict: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500

@app.post('/select_language')
def select_language():
    try:
        data = request.get_json()
        lang = data.get('language')
        logging.debug(f"Language selected: {lang}")
        if lang not in ['English', 'Arabic']:
            logging.error("Invalid language")
            return jsonify({'error': 'Invalid language'}), 400
        state = session.get('chat_state', {
            'state': 'language',
            'selected_language': None,
            'selected_tag': None,
            'user_name': None,
            'civil_id': None,
            'support_data': None
        })
        state['selected_language'] = lang
        state['state'] = 'name'
        session['chat_state'] = state
        response = PROMPTS[lang]['enter_name']
        chat = ChatMessage(
            session_id=session.sid,
            language=lang,
            sender='bot',
            message=response
        )
        db.session.add(chat)
        db.session.commit()
        logging.debug(f"Name prompt response: {response}")
        return jsonify({'answer': response})
    except Exception as e:
        logging.error(f"Error in select_language: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500
from flask import request, jsonify
from chat import get_response

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    message = data.get('msg')
    response = get_response(message)
    return jsonify({'response': response})

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            user = AdminUser.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for('admin'))
            return render_template('login.html', error='Invalid credentials')
        return send_from_directory(HTML_FOLDER, 'login.html')
    except Exception as e:
        logging.error(f"Error in login: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
@login_required
def logout():
    try:
        logout_user()
        return redirect(url_for('login'))
    except Exception as e:
        logging.error(f"Error in logout: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin')
@login_required
def admin():
    try:
        # Handle filter parameters
        language = request.args.get('language', None)
        department = request.args.get('department', None)
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)

        # Base queries
        chat_query = db.session.query(
            ChatMessage.session_id,
            ChatMessage.language,
            db.func.min(ChatMessage.timestamp).label('start_time'),
            db.func.count(ChatMessage.id).label('message_count')
        )
        support_query = db.session.query(SupportRequest)

        # Apply filters
        if language and language != 'All':
            chat_query = chat_query.filter(ChatMessage.language == language)
            support_query = support_query.filter(SupportRequest.language == language)
        if department and department != 'All':
            support_query = support_query.filter(SupportRequest.department == department)
        if start_date:
            start_date_dt = datetime.strptime(start_date, '%Y-%m-%d')
            chat_query = chat_query.filter(ChatMessage.timestamp >= start_date_dt)
            support_query = support_query.filter(SupportRequest.timestamp >= start_date_dt)
        if end_date:
            end_date_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            chat_query = chat_query.filter(ChatMessage.timestamp < end_date_dt)
            support_query = support_query.filter(SupportRequest.timestamp < end_date_dt)

        # Execute queries
        sessions = [{
            'session_id': row.session_id,
            'language': row.language or 'Unknown',
            'start_time': row.start_time.strftime('%Y-%m-%d %H:%M:%S') if row.start_time else 'N/A',
            'message_count': row.message_count
        } for row in chat_query.group_by(ChatMessage.session_id, ChatMessage.language).all()]
        support_requests = [{
            'session_id': req.session_id,
            'language': req.language or 'Unknown',
            'department': req.department,
            'name': req.name,
            'civil_id': req.civil_id,
            'contact_number': req.contact_number,
            'university': req.university or 'Not provided',
            'message': req.message,
            'timestamp': req.timestamp.strftime('%Y-%m-%d %H:%M:%S') if req.timestamp else 'N/A'
        } for req in support_query.all()]
        chat_count = db.session.query(ChatMessage.session_id).distinct().count()
        total_messages = ChatMessage.query.count()
        avg_messages = total_messages / chat_count if chat_count else 0
        language_dist = {lang: ChatMessage.query.filter_by(language=lang).count() for lang in ['English', 'Arabic', None]}

        # Analytics data
        departments = list(intents['intents']['English']['tags']['Support']['departments'].keys())
        department_counts = {dept: SupportRequest.query.filter_by(department=dept).count() for dept in departments}
        language_counts = {'English': language_dist['English'], 'Arabic': language_dist['Arabic'], 'Unknown': language_dist[None]}

        lang = current_user.username == 'admin' and 'English' or 'Arabic'
        logging.debug(f"Rendering admin dashboard with {len(sessions)} sessions and {len(support_requests)} support requests")
        return send_from_directory(HTML_FOLDER, 'admin.html', 
                              chat_count=chat_count, 
                              total_messages=total_messages, 
                              avg_messages=round(avg_messages, 2), 
                              language_dist=language_dist, 
                              sessions=sessions,
                              support_requests=support_requests,
                              lang=lang,
                              PROMPTS=PROMPTS,
                              departments=departments,
                              department_counts=department_counts,
                              language_counts=language_counts)
    except Exception as e:
        logging.error(f"Error in admin: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/chats/<session_id>')
@login_required
def view_chat(session_id):
    try:
        chats = ChatMessage.query.filter_by(session_id=session_id).order_by(ChatMessage.timestamp).all()
        support_requests = SupportRequest.query.filter_by(session_id=session_id).all()
        return jsonify({
            'chats': [{
                'sender': chat.sender,
                'message': chat.message,
                'timestamp': chat.timestamp.strftime('%Y-%m-%d %H:%M:%S') if chat.timestamp else 'N/A',
                'language': chat.language
            } for chat in chats],
            'support_requests': [{
                'department': req.department,
                'name': req.name,
                'civil_id': req.civil_id,
                'contact_number': req.contact_number,
                'university': req.university or 'Not provided',
                'message': req.message,
                'timestamp': req.timestamp.strftime('%Y-%m-%d %H:%M:%S') if req.timestamp else 'N/A',
                'language': req.language
            } for req in support_requests]
        })
    except Exception as e:
        logging.error(f"Error in view_chat: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/clear_data', methods=['POST'])
@login_required
def clear_data():
    try:
        # Delete all records from ChatMessage and SupportRequest tables
        db.session.query(ChatMessage).delete()
        db.session.query(SupportRequest).delete()
        db.session.commit()
        logging.info("Chat and support request data cleared by admin")
        return jsonify({'success': True, 'message': 'All chat and support request data cleared successfully'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error clearing data: {str(e)}")
        return jsonify({'error': f"Failed to clear data: {str(e)}"}), 500

@app.route('/admin/export')
@login_required
def export_chats():
    try:
        chats = ChatMessage.query.all()
        si = StringIO()
        writer = csv.writer(si, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['Session ID', 'Language', 'Sender', 'Message', 'Timestamp'])
        for chat in chats:
            writer.writerow([chat.session_id, chat.language or 'Unknown', chat.sender, chat.message.replace('\n', ' '), chat.timestamp.strftime('%Y-%m-%d %H:%M:%S') if chat.timestamp else 'N/A'])
        output = si.getvalue()
        db.session.close()
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=chats_export.csv"}
        )
    except Exception as e:
        logging.error(f"Error in export_chats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/export_support')
@login_required
def export_support():
    try:
        support_requests = SupportRequest.query.all()
        si = StringIO()
        writer = csv.writer(si, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['Session ID', 'Language', 'Department', 'Name', 'Civil ID', 'Contact Number', 'University', 'Message', 'Timestamp'])
        for req in support_requests:
            writer.writerow([
                req.session_id,
                req.language or 'Unknown',
                req.department,
                req.name,
                req.civil_id,
                req.contact_number,
                req.university or 'Not provided',
                req.message.replace('\n', ' '),
                req.timestamp.strftime('%Y-%m-%d %H:%M:%S') if req.timestamp else 'N/A'
            ])
        output = si.getvalue()
        db.session.close()
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=support_requests_export.csv"}
        )
    except Exception as e:
        logging.error(f"Error in export_support: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            if not AdminUser.query.filter_by(username='admin').first():
                admin = AdminUser(username='admin')
                admin.set_password('admin123')  # Change this password!
                db.session.add(admin)
                db.session.commit()
            app.run(debug=True)
        except Exception as e:
            logging.error(f"Error starting app: {str(e)}")
            raise