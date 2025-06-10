from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, flash
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from models import db, Admin, Patient, ScanResult
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.image import load_img, img_to_array
from datetime import datetime
import os
import numpy as np

app = Flask(__name__)
app.secret_key = 'super-secret-key-123'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/lung_cancer_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Load the model
model = load_model('lung_cancer_model.h5')

# Initialize DB
db.init_app(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ----------------------
# Routes
# ----------------------

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
		
        admin = Admin.query.filter_by(email=email).first()
        if admin and admin.password == password:
            session['admin'] = admin.email
            return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials"


    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'admin' not in session:
        return redirect(url_for('login'))

    patients = Patient.query.all()
    return render_template('dashboard.html', patients=patients)
    
@app.route('/add_p')
def add_p():
    if 'admin' not in session:
        return redirect(url_for('login'))

    patients = Patient.query.all()
    return render_template('add_p.html', patients=patients)
    
@app.route('/view_p')
def view_p():
    if 'admin' not in session:
        return redirect(url_for('login'))

    patients = Patient.query.all()
    return render_template('view_p.html', patients=patients)

@app.route('/create_patient', methods=['POST'])
def create_patient():
    name = request.form['name']
    mobile = request.form['mobile']
    age = request.form['age']
    gender = request.form['gender']
    new_patient = Patient(name=name, age=age, gender=gender, mobile=mobile)

 # Check if patient already exists
    existing_patient = Patient.query.filter_by(mobile=mobile).first()
    if existing_patient:
        flash('A patient with this mobile already exists.', 'warning')
        return redirect(url_for('add_p'))

    db.session.add(new_patient)
    db.session.commit()
    return redirect(url_for('view_p'))



@app.route('/delete_scan/<int:scan_id>', methods=['POST'])
def delete_scan(scan_id):
    scan = ScanResult.query.get(scan_id)
    if scan:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], scan.image_filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        db.session.delete(scan)
        db.session.commit()
    return redirect(url_for('patient_history', patient_id=scan.patient_id))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
	
@app.route('/upload/<int:patient_id>', methods=['POST'])
def upload_scan(patient_id):
    if 'admin' not in session:
        return redirect(url_for('login'))

    file = request.files['image']
    if file:
        patient = Patient.query.get_or_404(patient_id)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{secure_filename(patient.name)}_{timestamp}.jpg"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Process and predict
        img = load_img(filepath, target_size=(224, 224))
        img_array = img_to_array(img) / 255.0
        img_array = np.expand_dims(img_array, axis=0)
        prediction = model.predict(img_array)[0][0]
        result = "Negative for Lung Cancer" if prediction > 0.5 else "Positive for Lung Cancer"

        # Save to DB
        scan = ScanResult(patient_id=patient.id, image_filename=filename, result=result)
        db.session.add(scan)
        db.session.commit()

        flash(f"Prediction: {result}", "success")

    return redirect(url_for('patient_history', patient_id=patient_id))


@app.route('/patient_history')
def patient_history():
    if 'admin' not in session:
        return redirect(url_for('login'))

    patient_id = request.args.get('patient_id')
    patient = Patient.query.get(patient_id)
    scans = ScanResult.query.filter_by(patient_id=patient_id).all()

    return render_template('patient_history.html', patient=patient, scans=scans)

if __name__ == '__main__':
    app.run(debug=True)