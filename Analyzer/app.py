import streamlit as st
import base64
import os
import docx
import random
import numpy as np
import fitz  # PyMuPDF
from fpdf import FPDF
from PIL import Image
import re
import html
import string
import shutil

# --- High-Performance OCR Fallbacks ---
try:
    from rapidocr_onnxruntime import RapidOCR
    RAPIDOCR_AVAILABLE = True
except ImportError:
    RAPIDOCR_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
    
    # Auto-configure Tesseract path for Windows
    if os.name == 'nt':
        common_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Users\\' + os.getlogin() + r'\AppData\Local\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            r'C:\Tesseract-OCR\tesseract.exe'
        ]
        # Check session state for manual override first
        manual_path = st.session_state.get("manual_tess_path")
        if manual_path and os.path.exists(manual_path):
            pytesseract.pytesseract.tesseract_cmd = manual_path
        else:
            # Universal Tesseract discovery
            tess_path = shutil.which("tesseract")
            if tess_path:
                pytesseract.pytesseract.tesseract_cmd = tess_path
            else:
                for path in common_paths:
                    if os.path.exists(path):
                        pytesseract.pytesseract.tesseract_cmd = path
                        break
except ImportError:
    PYTESSERACT_AVAILABLE = False

def get_ocr_engine():
    """Lazy-load the OCR engine only when needed."""
    if not RAPIDOCR_AVAILABLE:
        return None
    try:
        return RapidOCR()
    except Exception:
        return None

def get_easyocr_reader():
    """Lazy-load EasyOCR reader."""
    if not EASYOCR_AVAILABLE:
        return None
    try:
        return easyocr.Reader(['en'], gpu=False)
    except Exception:
        return None

st.set_page_config(page_title="Resume Analyzer", layout="centered")

# -------------------------------
# Global Glassmorphism Styling
# -------------------------------
st.markdown("""
<style>
    .main-title {
        color: #9400D3;
        text-align: center;
        font-size: 40px;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .subtitle {
        color: #ffffff;
        text-align: center;
        font-size: 18px;
        margin-bottom: 20px;
    }
    .section-title {
        color: #ffffff;
        font-size: 24px;
        font-weight: bold;
        margin-top: 30px;
        margin-bottom: 15px;
        border-bottom: 2px solid rgba(255,255,255,0.3);
        padding-bottom: 5px;
    }
    .score-container {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        font-size: 24px;
        font-weight: bold;
        color: #ffffff;
        margin-top: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    .text-container {
        height: 300px;
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
        background-color: #27ae60;
    }
    .metric-card {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        text-align: center;
        margin-bottom: 10px;
    }
    .metric-card h4 {
        margin: 0;
        color: #e0e0e0 !important;
        font-size: 16px;
    }
    .metric-card h2 {
        margin: 10px 0 0 0;
        color: #ffffff !important;
        font-size: 28px;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------
# Core Data Extraction Logic
# -------------------------------
def extract_text(file):
    text = ""
    ocr_missing = False
    st.session_state.extraction_logs = []

    if file.type == "application/pdf":
        try:
            # Using PyMuPDF (fitz) - No Poppler required!
            doc = fitz.open(stream=file.read(), filetype="pdf")
            for idx, page in enumerate(doc):
                page_text = page.get_text()
                
                if page_text and page_text.strip():
                    text += page_text + "\n"
                else:
                    # OCR Fallback for Scanned PDFs (Native to PyMuPDF)
                    try:
                        # Render page to image at high res (300 DPI)
                        pix = page.get_pixmap(dpi=300)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        img_np = np.array(img)
                        
                        # 1. Try RapidOCR
                        ocr_engine = get_ocr_engine()
                        page_captured = False
                        if ocr_engine:
                            result, _ = ocr_engine(img_np)
                            if result:
                                text += "\n".join([line[1] for line in result]) + "\n"
                                page_captured = True
                        
                        # 2. Try EasyOCR (Stronger)
                        if not page_captured and EASYOCR_AVAILABLE:
                            reader = get_easyocr_reader()
                            if reader:
                                results = reader.readtext(img_np)
                                if results:
                                    text += "\n".join([res[1] for res in results]) + "\n"
                                    page_captured = True
                                    
                        # 3. Try Pytesseract
                        if not page_captured and PYTESSERACT_AVAILABLE:
                            text += pytesseract.image_to_string(img)
                            if text.strip(): page_captured = True
                            
                        if not page_captured:
                            ocr_missing = True
                    except Exception as e:
                        st.session_state.extraction_logs.append(f"P{idx+1} OCR Error: {str(e)}")
                        ocr_missing = True
            doc.close()
        except Exception as e:
            st.session_state.extraction_logs.append(f"PDF Error: {str(e)}")
            return ""

    elif file.type.endswith("document.wordprocessingml.document"):
        try:
            doc = docx.Document(file)
            for p in doc.paragraphs:
                if p.text: text += p.text + "\n"
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text: text += cell.text + "\n"
        except Exception as e:
            st.session_state.extraction_logs.append(f"DOCX Error: {str(e)}")

    elif file.type.startswith("image"):
        try:
            img = Image.open(file)
            img_np = np.array(img.convert('RGB'))
            page_captured = False
            
            ocr_engine = get_ocr_engine()
            if ocr_engine:
                result, _ = ocr_engine(img_np)
                if result: 
                    text += "\n".join([line[1] for line in result]) + "\n"
                    page_captured = True
            
            if not page_captured and EASYOCR_AVAILABLE:
                reader = get_easyocr_reader()
                if reader:
                    results = reader.readtext(img_np)
                    if results:
                        text += "\n".join([res[1] for res in results]) + "\n"
                        page_captured = True

            if not page_captured and PYTESSERACT_AVAILABLE:
                res = pytesseract.image_to_string(img)
                if res.strip():
                    text += res
                    page_captured = True

            if not page_captured: ocr_missing = True
        except Exception as e:
            st.session_state.extraction_logs.append(f"Image Error: {str(e)}")
            ocr_missing = True
            
    if ocr_missing:
        st.session_state.extraction_logs.append("⚠️ Could not read text from some pages. Ensure they are clear.")

    return text

# -------------------------------
# Detect Resume Sections
# -------------------------------
def analyze_resume(text):
    t = text.lower()
    has_email = bool(re.search(r'[\w\.-]+@[\w\.-]+', text))
    has_phone = bool(re.search(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', text))
    has_linkedin = "linkedin.com" in t

    sections_found = {
        "Contact Info": has_email or has_phone or has_linkedin,
        "Skills": bool(re.search(r'\b(skills|technical|technologies|proficiencies|expertise|knowledge)\b', t)),
        "Experience": bool(re.search(r'\b(experience|work history|employment|career|professional background)\b', t)),
        "Education": bool(re.search(r'\b(education|academic|university|degree|qualifications)\b', t)),
        "Projects": bool(re.search(r'\b(projects|portfolio|personal work|accomplishments)\b', t)),
        "Summary": bool(re.search(r'\b(summary|objective|profile|about me|professional profile)\b', t))
    }
    return sections_found

# -------------------------------
# Resume Score Calculation
# -------------------------------
def calculate_score(sections, text, target_role=""):
    details = {}
    t = text.lower()
    tr = target_role.lower()

    formatting = 0
    if len(text.split("\n")) > 12: formatting += 10
    if any(char in text for char in ["•", "-", "*", "·", "▪", "–", "—"]): formatting += 10
    details["Formatting"] = formatting

    content = 0
    words = len(text.split())
    if words > 200: content += 10
    if sections.get("Contact Info", False): content += 10
    details["Content"] = content

    skills_score = 0
    if sections.get("Skills", False): skills_score += 10
    keywords = [
        "python", "java", "javascript", "react", "node", "sql", "nosql", "aws",
        "azure", "docker", "kubernetes", "machine learning", "data", "ai", "agile", "scrum", "git", "ci/cd", 
        "project management", "leadership", "communication", "problem solving", "analytics"
    ]
    # Add words from target role
    role_words = [w for w in tr.split() if len(w) > 3]
    keywords.extend(role_words)

    matches = [kw for kw in keywords if kw in t]
    skills_score += min(20, len(matches) * 2) 
    details["Skills"] = skills_score

    exp_score = 0
    if sections.get("Experience", False): exp_score += 15
    impact_verbs = ["managed", "led", "developed", "increased", "reduced", "spearheaded", "optimized", "implemented"]
    if any(v in t for v in impact_verbs): exp_score += 5
    if re.search(r'\d+%', text) or re.search(r'\$\d+', text) or re.search(r'\b(years|months)\b', t):
        exp_score += 10
    details["Experience"] = exp_score

    total = formatting + content + skills_score + exp_score
    return details, min(total, 100)

# -------------------------------
# Suggestions
# -------------------------------
def generate_suggestions(sections, text, target_role=""):
    suggestions = []
    if target_role:
        suggestions.append(f"Tailor your summary to highlight qualifications for the '{target_role}' role.")
    if not sections["Summary"]:
        suggestions.append("Add a professional summary at the top.")
    if not sections["Skills"]:
        suggestions.append("Include a technical skills section.")
    if target_role:
        tr_words = [w for w in target_role.lower().split() if len(w) > 3]
        missing_role_words = [w for w in tr_words if w not in text.lower()]
        if missing_role_words:
            suggestions.append(f"Consider adding role-specific skills: {', '.join(missing_role_words)}")
    if not sections["Projects"]:
        suggestions.append("Add a projects section to show practical application.")
    if not re.search(r'\d+', text):
        suggestions.append("Quantify achievements (e.g., 'improved speed by 30%').")
    return suggestions

# -------------------------------
# Extract Bullet Points
# -------------------------------
def extract_bullets(text):
    bullets = []
    bullet_chars = ("•", "-", "*", "·", "▪", "–", "—", ">", "o ", "e ", "■", "♦")
    for line in text.split("\n"):
        line = line.strip()
        if len(line.split()) >= 5:
            if line.startswith(bullet_chars) or re.match(r'^[A-Z][a-z]+ed\b', line):
                bullets.append(line)
    return list(dict.fromkeys(bullets))[:15]

# -------------------------------
# Deep Analysis & Rewrite of Bullet Points
# -------------------------------
def improve_bullets(bullets, target_role="", jd_text=""):
    improved = []
    context_text = f"{target_role} {jd_text}".lower()
    words = re.sub(f'[{re.escape(string.punctuation)}]', ' ', context_text).split()
    stop_words = {"the", "and", "to", "of", "in", "for", "is", "with", "on", "as", "an", "at", "it", "or", "from", "be", "are", "you", "your", "we", "our"}
    role_keywords = list(set([w for w in words if w not in stop_words and len(w) > 3]))
    
    selected_bullets = random.sample(bullets, min(len(bullets), 5))
    if not selected_bullets and target_role:
        return [] # Downstream will handle fallback

    for bullet in selected_bullets:
        clean_bullet = re.sub(r'^[\s\•\-\*\·\▪\–\—\>]+', '', bullet).strip()
        bullet_words = clean_bullet.split()
        first_word = bullet_words[0].lower() if bullet_words else ""
        has_metrics = bool(re.search(r'\d+', clean_bullet) or '%' in clean_bullet)
        
        weak_to_strong = {"helped": "Spearheaded", "worked": "Engineered", "did": "Executed", "managed": "Optimized", "led": "Pioneered", "used": "Leveraged"}
        suggestions = []
        rewrite = clean_bullet
        
        if first_word in weak_to_strong:
            strong = weak_to_strong[first_word]
            suggestions.append(f"- Use '{strong}' instead of '{first_word}'.")
            rewrite = re.sub(rf'^{first_word}', strong, rewrite, count=1, flags=re.IGNORECASE)
            
        if not has_metrics:
            impact = random.choice(["resulting in 20% efficiency gain.", "reducing processing time by 15%.", "saving $5k in monthly overhead."])
            suggestions.append("- Add numerical impact.")
            rewrite = rewrite.rstrip('.') + f", {impact}"
            
        if role_keywords:
            kw = random.choice(role_keywords).capitalize()
            if kw.lower() not in rewrite.lower():
                suggestions.append(f"- Align to '{target_role}' by mentioning '{kw}'.")
                rewrite = rewrite.rstrip('.') + f" while maintaining {kw} standards."

        improved.append(f"*{clean_bullet}*\n  **Analysis:**\n  {chr(10).join(suggestions)}\n\n  [REWRITE]: {rewrite}")
    return improved

def generate_fallback_bullets(text, target_role=""):
    base = target_role if target_role else "Professional"
    return [
        f"Spearheaded {base} initiatives resulting in a 25% increase in operational throughput.",
        f"Optimized core workflows for {base} environments, reducing error rates by 15%.",
        f"Collaborated on {base} projects, delivering results 10% ahead of schedule.",
        f"Engineered scalable solutions tailored to {base} standards.",
        f"Pioneered data-driven strategies for {base} excellence."
    ]

def ats_match(resume_text, jd_text, target_role=""):
    full_target = f"{target_role} {jd_text}"
    if not full_target.strip(): return 0
    def clean(text):
        text = text.lower()
        text = re.sub(f'[{re.escape(string.punctuation)}]', ' ', text)
        stop = {"the", "and", "to", "of", "in", "for", "is", "with", "on", "as", "an", "at", "by", "this", "it", "or", "from", "be", "are", "we", "our"}
        return {w for w in text.split() if w not in stop and len(w) > 2}
    res_w = clean(resume_text)
    jd_w = clean(full_target)
    if not jd_w: return 0
    match = len(res_w.intersection(jd_w))
    role_w = clean(target_role)
    role_m = len(res_w.intersection(role_w))
    perc = ((match + role_m) / (len(jd_w) + max(1, len(role_w)))) * 100
    return min(100, round(perc * 1.5))

# -------------------------------
# Dashboard Rendering
# -------------------------------
def set_bg_from_local(image_file, blur=False, font_color=None):
    base_path = os.path.dirname(os.path.abspath(__file__))
    absolute_path = os.path.join(base_path, image_file)
    encoded = ""
    if os.path.exists(absolute_path):
        with open(absolute_path, "rb") as f: encoded = base64.b64encode(f.read()).decode()
    css = "<style>\n.stApp {\n"
    if encoded: css += f"background-image: url(data:image/png;base64,{encoded});\n"
    else: css += "background: radial-gradient(circle, #2C5364 0%, #0F2027 100%);\n"
    css += "background-size: cover; background-position: center; background-attachment: fixed; }\n"
    if blur:
        css += """
        .block-container {
            backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px);
            background-color: rgba(50, 80, 90, 0.7); border-radius: 20px;
            padding: 3rem !important; border: 1px solid rgba(255,255,255,0.1);
        }
        """
    if font_color:
        css += f".block-container * {{ color: {font_color} !important; }}\n"
        css += "[data-testid='stFileUploadDropzone'] * { color: #ffffff !important; }\n"
    css += "</style>"
    st.markdown(css, unsafe_allow_html=True)

# -------------------------------
# SIDEBAR DIAGNOSTICS
# -------------------------------
with st.sidebar:
    st.markdown("### 🛠️ System Status")
    env_type = "Windows (Local)" if os.name == 'nt' else "Linux (Cloud)"
    st.caption(f"Environment: {env_type}")
    
    with st.expander("Diagnostics"):
        st.write("PyMuPDF: ✅ Active")
        
        # RapidOCR check
        if RAPIDOCR_AVAILABLE: st.write("RapidOCR: ✅ Found")
        else:
            st.write("RapidOCR: ❌ Missing")
            if os.name == 'nt': st.caption("Run: pip install rapidocr-onnxruntime")
            else: st.caption("Missing libgl1 in packages.txt?")
        
        # Tesseract check with Manual Override
        tess_path = getattr(pytesseract.pytesseract, 'tesseract_cmd', 'tesseract')
        if shutil.which(tess_path) or (os.path.exists(tess_path) if os.name == 'nt' else False):
            st.write("Tesseract: ✅ Found")
            st.caption(f"Path: {tess_path}")
        else:
            st.write("Tesseract: ❌ Bin Missing")
            if os.name == 'nt':
                st.info("I couldn't find Tesseract automatically. Please paste the path below:")
                new_path = st.text_input("Manual Tesseract Path", 
                                       value=st.session_state.get("manual_tess_path", r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
                                       key="manual_tess_path_input")
                if st.button("Apply & Verify Path"):
                    st.session_state["manual_tess_path"] = new_path
                    st.rerun()
                st.link_button("Download Tesseract (.exe)", "https://github.com/UB-Mannheim/tesseract/wiki")
            else:
                st.caption("Add tesseract-ocr to packages.txt")

    if st.button("Reset App"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

# -------------------------------
# PAGE 1 : Upload
# -------------------------------
if "page" not in st.session_state: st.session_state.page = "upload"

if st.session_state.page == "upload":
    set_bg_from_local("background.png", blur=True, font_color="#ffffff")
    st.markdown('<div class="main-title">📄 Resume Analyzer & Improver</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Enter your target job role, then upload your resume for ATS analysis.</div>', unsafe_allow_html=True)
    st.markdown("### 1. Target Job Role")
    st.markdown("What job role are you applying for? (e.g., Python Developer, Data Scientist)")
    tr = st.text_input("target_role", label_visibility="collapsed", placeholder="Enter job role...")
    st.markdown("### 2. Job Description (Optional)")
    st.markdown("Paste the Job Description (JD) here for a more precise match.")
    jd = st.text_area("jd", label_visibility="collapsed", height=150)
    st.markdown("### 3. Upload Resume")
    st.markdown("Upload your resume in PDF, DOCX, JPG, or PNG format.")
    file = st.file_uploader("Upload Resume", type=["pdf","docx","jpg","png"], label_visibility="collapsed")
    if file and st.button("🔍 Analyze Resume", use_container_width=True):
        st.session_state.text = extract_text(file)
        st.session_state.target_role = tr
        st.session_state.jd = jd
        st.session_state.page = "analysis"
        st.rerun()

# -------------------------------
# PAGE 2 : Analysis
# -------------------------------
elif st.session_state.page == "analysis":
    set_bg_from_local("background2.png", blur=True, font_color="#ffffff")
    text = st.session_state.text
    tr = st.session_state.target_role
    jd = st.session_state.jd

    st.markdown(f'<div class="section-title">Analysis Executive Summary {f"for {tr}" if tr else ""}</div>', unsafe_allow_html=True)
    
    # 📝 Show extraction logs ALWAYS if they exist (for debugging)
    if st.session_state.get('extraction_logs'):
        with st.expander("📝 View Extraction Warnings (Debug Info)", expanded=True):
            for log in st.session_state['extraction_logs']:
                st.warning(log)
    
    words = len(text.split())
    if words < 50:
        st.error("🚨 Error: No text could be extracted. Please ensure the file is not corrupted or scanned without OCR support.")
        if st.button("Try Another"):
            st.session_state.page = "upload"; st.rerun()
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**Word Count**: {words}")
            st.write(f"**Readability**: {'High' if words > 300 else 'Medium'}")
        with c2:
            sc = analyze_resume(text)
            det = [k for k, v in sc.items() if v]
            st.write(f"**Sections Found**: {len(det)} / 6")
            st.write(f"**Status**: {'Ready for ATS' if len(det) >= 4 else 'Needs Improvement'}")

        if tr or jd:
            st.markdown('<div class="section-title">Target Job ATS Match Score</div>', unsafe_allow_html=True)
            score = ats_match(text, jd, tr)
            st.progress(score)
            st.markdown(f"### ATS Match to **{tr if tr else 'JD'}**: **{score}%**")

        st.markdown('<div class="section-title">Extracted Resume Text</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="text-container">{html.escape(text)}</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Resume Overview Score</div>', unsafe_allow_html=True)
        det_s, tot_s = calculate_score(sc, text, tr)
        cl1, cl2 = st.columns(2)
        m_style = "<div class='metric-card'><h4>{}</h4><h2>{} <span style='font-size:16px;color:#e0e0e0;'>/ {}</span></h2></div>"
        with cl1:
            st.markdown(m_style.format("Formatting", det_s['Formatting'], 20), unsafe_allow_html=True)
            st.markdown(m_style.format("Content Quality", det_s['Content'], 30), unsafe_allow_html=True)
        with cl2:
            st.markdown(m_style.format("Skills Relevance", det_s['Skills'], 25), unsafe_allow_html=True)
            st.markdown(m_style.format("Experience Impact", det_s['Experience'], 25), unsafe_allow_html=True)
        st.progress(tot_s)
        st.markdown(f'<div class="score-container">Final Resume Score: {tot_s} / 100</div>', unsafe_allow_html=True)

        # -------------------------------
        # Suggestions
        # -------------------------------
        st.markdown('<div class="section-title">Improvement Suggestions</div>', unsafe_allow_html=True)
        suggestions = generate_suggestions(sc, text, tr)
        if suggestions:
            for s in suggestions:
                st.info(s)
        else:
            st.success("Your resume structure looks strong!")

        # -------------------------------
        # Bullet Improvements
        # -------------------------------
        st.markdown('<div class="section-title">Target Role Driven Bullet Rewrite</div>', unsafe_allow_html=True)
        bul = extract_bullets(text)
        imp_bul = improve_bullets(bul, tr, jd) if bul else []
        final_bul = imp_bul if imp_bul else [f"- {b}" for b in generate_fallback_bullets(text, tr)]
        for b in final_bul: st.markdown(b)

        st.markdown("---")
        report = f"RESUME REPORT: {tr}\nATS Score: {score}%\nOverall: {tot_s}/100\n\nREWRITTEN BULLETS:\n"
        for b in final_bul:
            line = b.split("[REWRITE]:")[-1].strip() if "[REWRITE]:" in b else b.replace("- ", "")
            report += f"- {line}\n"
        
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 7, report.encode('latin-1', 'replace').decode('latin-1'))
        st.download_button("📥 Download Report (PDF)", bytes(pdf.output()), f"Resume_Report_{tr}.pdf", "application/pdf")
        if st.button("Analyze Another"):
            st.session_state.page = "upload"; st.rerun()
