import streamlit as st
import base64
import os
import pdfplumber
import docx
import random
import re
import html
import string
from fpdf import FPDF
from PIL import Image

st.set_page_config(page_title="Resume Analyzer", layout="centered")

# -------------------------------
# Global Styling (Transparent Glassmorphism)
# -------------------------------
st.markdown("""
<style>
    .main-title {
        color: #FFFFFF;
        text-align: center;
        font-size: 40px;
        font-weight: bold;
        margin-bottom: 10px;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
    }
    .subtitle {
        color: #E0E0E0;
        text-align: center;
        font-size: 18px;
        margin-bottom: 20px;
    }
    .section-title {
        color: #FFFFFF;
        font-size: 26px;
        font-weight: bold;
        margin-top: 30px;
        margin-bottom: 20px;
        border-bottom: 2px solid rgba(255,255,255,0.4);
        padding-bottom: 8px;
        text-shadow: 0px 2px 4px rgba(0,0,0,0.5);
    }
    .score-container {
        background: rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(15px);
        padding: 25px;
        border-radius: 15px;
        text-align: center;
        font-size: 26px;
        font-weight: bold;
        color: #00FFCC;
        margin-top: 25px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    .text-container {
        height: 250px;
        overflow-y: scroll;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 8px;
        padding: 15px;
        background: rgba(0, 0, 0, 0.2);
        white-space: pre-wrap;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
        color: #ffffff !important;
    }
    .stProgress > div > div > div > div {
        background-color: #00FFCC;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------
# Simplified Text Extraction
# -------------------------------
def extract_text(file):
    text = ""
    if file.type == "application/pdf":
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    elif file.type.endswith("document.wordprocessingml.document"):
        doc = docx.Document(file)
        for p in doc.paragraphs:
            text += p.text + "\n"
    return text

# -------------------------------
# ATS Match calculation
# -------------------------------
def ats_match(resume_text, jd_text, target_role=""):
    full_target = f"{target_role} {jd_text}"
    if not full_target.strip():
        return 0

    def clean(text):
        text = text.lower()
        text = re.sub(f'[{re.escape(string.punctuation)}]', ' ', text)
        words = text.split()
        stop_words = {"the", "and", "a", "to", "of", "in", "for", "is", "with", "on", "as", "an", "by", "at", "this", "that", "it", "or", "from", "be", "are", "you", "your", "we", "our", "will", "can", "their"}
        return {w for w in words if w not in stop_words and len(w) > 2}

    resume_words = clean(resume_text)
    jd_words = clean(full_target)
    
    if not jd_words:
        return 0

    match_count = len(resume_words.intersection(jd_words))
    role_words = clean(target_role)
    role_match = len(resume_words.intersection(role_words))
    
    match_percentage = ((match_count + (role_match * 2)) / (len(jd_words) + 1)) * 100
    return min(100, round(match_percentage * 1.8))

# -------------------------------
# AI Suggestions (Keywords)
# -------------------------------
def get_missing_keywords(resume_text, jd_text, target_role=""):
    full_target = f"{target_role} {jd_text}".lower()
    resume_text = resume_text.lower()
    
    # Standard technical keywords for broad analysis
    tech_keywords = ["python", "java", "sql", "aws", "cloud", "agile", "project management", "react", "c++", "data analysis"]
    
    tr_words = [w for w in target_role.lower().split() if len(w) > 3]
    jd_words = [w for w in re.sub(r'[^\w\s]', '', jd_text.lower()).split() if len(w) > 4]
    
    potential_keywords = list(set(tech_keywords + tr_words + jd_words))
    missing = [kw for kw in potential_keywords if kw not in resume_text][:8]
    return missing

# -------------------------------
# AI Bullet Rewrites
# -------------------------------
def improve_bullets(resume_text, target_role=""):
    # Simulated AI Bullet generation based on resume content
    bullet_chars = ("•", "-", "*", "·")
    raw_lines = [l.strip() for l in resume_text.split('\n') if len(l.split()) > 5]
    
    # Filter for past-tense action lines
    base_bullets = [l for l in raw_lines if any(l.startswith(c) for c in bullet_chars) or re.match(r'^[A-Z][a-z]+ed\b', l)]
    
    if not base_bullets:
        base_bullets = raw_lines[:5]
    
    # Select 4-5
    selected = base_bullets[:5]
    improved = []
    
    verbs = ["Spearheaded", "Orchestrated", "Engineered", "Optimized", "Catalyzed", "Pioneered"]
    metrics = ["resulting in a 25% efficiency boost.", "reducing operational costs by 15%.", "ahead of schedule by 2 weeks.", "increasing overall system performance by 20%."]
    
    for i, bullet in enumerate(selected):
        clean = re.sub(r'^[\s\•\-\*]+', '', bullet).strip()
        verb = random.choice(verbs)
        metric = random.choice(metrics)
        role_mention = f" for the {target_role} role" if target_role and i % 2 == 0 else ""
        
        rewrite = f"{verb} {clean.lower().rstrip('.')}{role_mention}, {metric}"
        improved.append({
            "original": clean,
            "rewrite": rewrite
        })
        
    # Pad to 4 if too few
    while len(improved) < 4:
        improved.append({
            "original": "N/A (Generic Addition)",
            "rewrite": f"Collaborated with cross-functional teams to deliver high-impact {target_role if target_role else 'business'} solutions."
        })
        
    return improved[:5]

# -------------------------------
# Background Helper
# -------------------------------
def set_bg_from_local(image_file, blur=False, font_color=None):
    base_path = os.path.dirname(os.path.abspath(__file__))
    absolute_path = os.path.join(base_path, image_file)
    encoded_string = ""
    if os.path.exists(absolute_path):
        with open(absolute_path, "rb") as file:
            encoded_string = base64.b64encode(file.read()).decode()

    css = "<style>\n.stApp {\n"
    if encoded_string:
        css += f"background-image: url(data:image/png;base64,{encoded_string});\n"
    else:
        css += "background: radial-gradient(circle, #2C5364 0%, #203A43 50%, #0F2027 100%);\n"
    
    css += "background-size: cover; background-position: center; background-attachment: fixed; }\n"
    
    if blur:
        css += ".block-container { backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px); background-color: rgba(50, 80, 90, 0.7); border-radius: 20px; padding: 3rem !important; box-shadow: 0 8px 32px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); }\n"
        
    if font_color:
        css += f".block-container p, .block-container h1, .block-container h2, .block-container h3, .block-container h4, .subtitle, .main-title {{ color: {font_color} !important; }}\n"
        css += "[data-testid=\"stFileUploadDropzone\"] * { color: #ffffff !important; }\n"
        
    css += "</style>"
    st.markdown(css, unsafe_allow_html=True)

# -------------------------------
# APP ROUTING
# -------------------------------
if "page" not in st.session_state:
    st.session_state.page = "upload"

# PAGE : UPLOAD
if st.session_state.page == "upload":
    set_bg_from_local("background.png", blur=True, font_color="#ffffff")
    st.markdown('<div class="main-title">📄 ATS Resume Matcher</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Enter target role and upload resume for instant matching.</div>', unsafe_allow_html=True)
    
    target_role = st.text_input("1. Target Job Role", placeholder="e.g. Data Scientist")
    jd = st.text_area("2. Job Description (Optional)", height=150)
    file = st.file_uploader("3. Upload Resume", type=["pdf","docx"])
    
    if file and st.button("🚀 Analyze ATS Match", use_container_width=True):
        with st.spinner("AI is analyzing text..."):
            text = extract_text(file)
            if not text.strip():
                st.error("Could not extract text. Please use a text-based PDF/Word file.")
            else:
                st.session_state.text = text
                st.session_state.target_role = target_role
                st.session_state.jd = jd
                st.session_state.page = "analysis"
                st.rerun()

# PAGE : ANALYSIS
elif st.session_state.page == "analysis":
    set_bg_from_local("background2.png", blur=True, font_color="#ffffff")
    
    if 'text' not in st.session_state:
        st.session_state.page = "upload"
        st.rerun()

    text = st.session_state.text
    target_role = st.session_state.target_role
    jd = st.session_state.jd

    st.markdown(f'<div class="section-title">ATS Match Results: {target_role}</div>', unsafe_allow_html=True)
    
    score = ats_match(text, jd, target_role)
    st.progress(score)
    st.markdown(f'<div class="score-container">Overall ATS Score: {score}%</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### 🔍 Missing Keywords")
        missing = get_missing_keywords(text, jd, target_role)
        for m in missing:
            st.code(m)
            
    with col2:
        st.markdown("### 📄 Resume Content")
        st.markdown(f'<div class="text-container">{html.escape(text)}</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">✨ AI Bullet Point Rewrites</div>', unsafe_allow_html=True)
    improved = improve_bullets(text, target_role)
    
    report_text = f"RESUME IMPACT REPORT - {target_role}\nATS SCORE: {score}%\n\nREWRITTEN BULLETS:\n"
    for item in improved:
        with st.expander(f"Original: {item['original'][:60]}..."):
            st.write(f"**AI Rewrite**: {item['rewrite']}")
        report_text += f"- {item['rewrite']}\n\n"

    # PDF Download
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.multi_cell(0, 10, txt=report_text.encode('latin-1', 'replace').decode('latin-1'))
    
    st.download_button(
        label="📥 Download AI Improvement Report (PDF)",
        data=bytes(pdf.output()),
        file_name=f"ATS_Report_{target_role}.pdf",
        mime="application/pdf"
    )
    
    if st.button("⬅️ Upload New Resume"):
        st.session_state.page = "upload"
        st.rerun()
