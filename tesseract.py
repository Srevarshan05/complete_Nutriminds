import os
import logging
from flask import Flask, request, render_template, jsonify
from groq import Groq
import pytesseract
from PIL import Image
import csv

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Initialize Tesseract OCR
try:
    # Ensure Tesseract is installed and available in system PATH
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Update this path if needed (e.g., '/usr/bin/tesseract' on Linux)
    logging.info("Tesseract OCR initialized successfully")
except Exception as e:
    logging.error(f"Failed to initialize Tesseract OCR: {str(e)}")
    raise

try:
    client = Groq(api_key="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")
    logging.info("Groq client initialized successfully")
except Exception as e:
    logging.error(f"Failed to initialize Groq client: {str(e)}")
    raise

# Global variables (unchanged)
image_path = None
csv_path = 'data.csv'
log_csv_path = 'refined_text_log.csv'

# Original logic functions (modified only extract_and_clean_text for Tesseract)
def log_refined_text(refined_text):
    """
    Logs the refined OCR-extracted text into a CSV file.
    """
    try:
        with open(log_csv_path, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([refined_text])
        logging.debug(f"Logged refined text to {log_csv_path}")
    except Exception as e:
        logging.error(f"Error logging refined text: {str(e)}")
        raise

def extract_and_clean_text(image_path):
    """
    Extracts text from an image using Tesseract OCR and cleans it.
    """
    try:
        logging.debug(f"Processing image with Tesseract OCR: {image_path}")
        # Open image with PIL
        img = Image.open(image_path)
        # Extract text using Tesseract
        text = pytesseract.image_to_string(img, lang='eng')
        if not text.strip():
            logging.warning(f"No text detected in image: {image_path}")
            raise ValueError("No readable text detected in the image")
        
        logging.debug(f"Raw OCR text: {text}")
        # Split text into lines and clean
        lines = text.split('\n')
        cleaned_text = []
        for line in lines:
            line = line.strip()
            if len(line) >= 3 and line.isprintable():
                cleaned_text.append(line)
        logging.debug(f"Cleaned text: {cleaned_text}")
        return cleaned_text
    except Exception as e:
        logging.error(f"Error in extract_and_clean_text: {str(e)}")
        raise

def process_image_and_csv(image_path, csv_path):
    """
    Processes a nutritional image, sending data to the Groq API for analysis.
    """
    if not image_path:
        logging.error("No image path provided")
        return "Error: No image path provided!", "", ""
    try:
        # Extract text from the image
        cleaned_text = extract_and_clean_text(image_path)
        extracted_text = ", ".join(cleaned_text)
        logging.debug(f"Extracted text: {extracted_text}")

        # Sending the OCR text to NLP model
        prompt = f"""
        I am using OCR to extract the Nutritional information from the Food pack labels. 
        I need you to refine the text: {extracted_text}. Just return the nutritional facts and Ingredients. 
        Based on the ingredients, what is the Food name? No other words.
        """

        # Send the prompt to Groq
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": "You are a professional medical advisor."},
                      {"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
            top_p=1,
            stream=False
        )
        logging.debug(f"Groq response: {response}")
        refined_text = response.choices[0].message.content
        log_refined_text(refined_text)
        return refined_text, "", ""
    except Exception as e:
        logging.error(f"Error in process_image_and_csv: {str(e)}")
        return f"Error occurred: {str(e)}", "", ""

# Flask setup
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB file size limit

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_nutritional', methods=['POST'])
def upload_nutritional():
    global image_path
    if 'file' not in request.files:
        logging.error("No file part in request")
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files['file']
    if file.filename == '':
        logging.error("No file selected")
        return jsonify({"error": "No file selected"}), 400
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        logging.debug(f"Saving file to: {filepath}")
        file.save(filepath)
        if not os.path.exists(filepath):
            logging.error("File save failed")
            return jsonify({"error": "Failed to save the uploaded file"}), 500
        image_path = filepath
        refined_text, _, _ = process_image_and_csv(image_path, csv_path)
        if refined_text.startswith("Error occurred:"):
            logging.error(f"Processing failed: {refined_text}")
            return jsonify({"error": refined_text}), 500
        logging.info("Nutritional image processed successfully")
        return jsonify({"refined_text": refined_text, "image_url": f"/{filepath}"})
    except Exception as e:
        logging.error(f"Upload nutritional error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/upload_medical', methods=['POST'])
def upload_medical():
    if 'file' not in request.files:
        logging.error("No file part in request")
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files['file']
    if file.filename == '':
        logging.error("No file selected")
        return jsonify({"error": "No file selected"}), 400
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        logging.debug(f"Saving file to: {filepath}")
        file.save(filepath)
        if not os.path.exists(filepath):
            logging.error("File save failed")
            return jsonify({"error": "Failed to save the uploaded file"}), 500
        extracted_text = extract_and_clean_text(filepath)
        medical_prompt = f"""
        I am using OCR to extract the text from a medical report. 
        Refine the text: {extracted_text}, remove any noise, and provide a clear summary of the medical findings. 
        Just return the important medical details and diagnosis if available, no extra words.
        """
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": "You are a professional medical advisor."},
                      {"role": "user", "content": medical_prompt}],
            temperature=0.7,
            max_tokens=300,
            top_p=1,
            stream=False
        )
        logging.info("Medical report processed successfully")
        return jsonify({"refined_text": response.choices[0].message.content})
    except Exception as e:
        logging.error(f"Upload medical error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/evaluate_combined', methods=['POST'])
def evaluate_combined():
    data = request.json
    nutritional_text = data.get('nutritional_text', '').strip()
    medical_text = data.get('medical_text', '').strip()
    selected_model = data.get('model', 'llama-3.3-70b-versatile')
    selected_language = data.get('language', 'English')

    if not nutritional_text:
        logging.error("No nutritional text provided")
        return jsonify({"error": "Please analyze nutritional data first"}), 400
    if not medical_text:
        logging.error("No medical text provided")
        return jsonify({"error": "Please process medical report first"}), 400

    try:
        next_prompt = f"""
        Dear User,

        Based on the extracted text from your food pack labels: {nutritional_text},
        and the details from your medical report: {medical_text},
        please evaluate the ingredients for safety.
        Provide a short recommendation on whether the food is safe to consume,
        including the safe quantity for intake if applicable.
        If the food is not recommended, briefly explain why it should be avoided.

        Please provide the response in the following format:

        1. First, a short and clear recommendation in **English**.
        2. After that, a short and clear recommendation in **{selected_language}** that corresponds to the English response.
        """
        final_response = client.chat.completions.create(
            model=selected_model,
            messages=[{"role": "system", "content": "You are a professional medical advisor."},
                      {"role": "user", "content": next_prompt}],
            temperature=0.7,
            max_tokens=400,
            top_p=1,
            stream=False
        )
        logging.info("Combined evaluation completed successfully")
        return jsonify({"result": final_response.choices[0].message.content})
    except Exception as e:
        logging.error(f"Evaluate combined error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == "__main__":
    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        logging.info(f"Upload folder created/verified: {UPLOAD_FOLDER}")
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logging.error(f"Startup error: {str(e)}")