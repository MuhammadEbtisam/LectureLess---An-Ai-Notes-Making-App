import streamlit as st
import google.generativeai as genai
import tempfile
import os
import time
from youtube_transcript_api import YouTubeTranscriptApi
import PyPDF2
import docx
import re
import markdown
from xhtml2pdf import pisa
from io import BytesIO

# Configure Page
st.set_page_config(page_title="The Lecture Refactorer", page_icon="📚", layout="wide")

# Custom CSS for aesthetics
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
        color: #e0e0e0;
    }
    .stButton>button {
        width: 100%;
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #45a049;
        transform: scale(1.02);
    }
    h1, h2, h3 {
        color: #4CAF50;
    }
    .glass-container {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 20px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# API configuration
# Try to get API key from streamlit secrets (for cloud deployment)
# Fallback to hardcoded key if not found
API_KEY = st.secrets.get("GEMINI_API_KEY", "AIzaSyC5qQodjGAhYVqo26inXaJBlKcKUHiaorM")
genai.configure(api_key=API_KEY)

# Load System Prompt
@st.cache_data
def load_system_prompt():
    # Try local path first, then relative path (for cloud deployment)
    prompt_paths = [
        r"d:\CODING\NOTES GENERATOR\SYSTEM PROMPTS\3.md",
        "3.md",
        "../3.md"
    ]
    for path in prompt_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    
    st.error("System prompt file (3.md) not found in any expected location.")
    return "You are The Lecture Refactorer."

SYSTEM_PROMPT = load_system_prompt()

# Utility Functions
def clean_markdown(text):
    # Remove excessive newlines (more than 2 to just 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def generate_pdf(md_text):
    html_content = markdown.markdown(md_text, extensions=['fenced_code', 'tables', 'sane_lists'])
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        @page {{ size: a4; margin: 2cm; }}
        body {{ font-family: sans-serif; line-height: 1.5; font-size: 12px; }}
        h1, h2, h3 {{ color: #333; }}
        pre {{ background-color: #f4f4f4; padding: 10px; border-radius: 5px; }}
        code {{ background-color: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-family: monospace; font-size: 10px; }}
        blockquote {{ border-left: 4px solid #ccc; margin: 0; padding-left: 10px; color: #666; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; }}
        th {{ background-color: #f2f2f2; text-align: left; }}
    </style>
    </head>
    <body>
    {html_content}
    </body>
    </html>
    """
    
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
    if pisa_status.err:
        return None
    return pdf_buffer.getvalue()

def extract_yt_transcript(url):
    try:
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]
        else:
            return None, "Invalid YouTube URL"
        
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript = " ".join([d['text'] for d in transcript_list])
        return transcript, None
    except Exception as e:
        return None, str(e)

def extract_text_from_pdf(file):
    reader = PyPDF2.PdfReader(file)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

def extract_text_from_docx(file):
    doc = docx.Document(file)
    return "\n".join([para.text for para in doc.paragraphs])

# Model Config
generation_config = {
  "temperature": 0.5, # Slightly lower for analytical notes
  "top_p": 0.95,
  "top_k": 64,
  "max_output_tokens": 8192,
}

# The user explicitly asked to use "gemini 2.5 flash lite"
model_name = "gemini-2.5-flash-lite"
# If lite is unavailable in specific regions, fallback to standard gemini-2.5-flash
# but we will try the exact lite model first as requested.

st.markdown("<div class='glass-container'>", unsafe_allow_html=True)
st.title("📚 The Lecture Refactorer")
st.markdown("Transform messy lectures, videos, and documents into elegant, descriptive, **'geek-to-geek'** style notes. Powered by Gemini 2.5 Flash Lite ⚡.")
st.markdown("</div>", unsafe_allow_html=True)

# User Input Section
st.markdown("### 1. Select Content Source")
input_type = st.radio("Choose how you want to provide the lecture content:", 
                      ["YouTube Video Link", "Video File Upload", "Document Upload (PDF/DOCX/TXT)", "Raw Transcript", "Topic Name Only"],
                      horizontal=True)

st.markdown("### 2. Provide Content")
user_input_text = ""
uploaded_file = None
yt_url = ""

if input_type == "YouTube Video Link":
    yt_url = st.text_input("🔗 Enter YouTube URL:", placeholder="https://www.youtube.com/watch?v=...")
elif input_type == "Video File Upload":
    uploaded_file = st.file_uploader("🎬 Upload Video File (Max 2GB approx for Gemini)", type=['mp4', 'mkv', 'avi', 'mov'])
elif input_type == "Document Upload (PDF/DOCX/TXT)":
    uploaded_file = st.file_uploader("📄 Upload Document", type=['pdf', 'docx', 'txt'])
elif input_type == "Raw Transcript":
    user_input_text = st.text_area("📝 Paste Transcript Here:", height=200, placeholder="Start typing or pasting here...")
elif input_type == "Topic Name Only":
    user_input_text = st.text_input("💡 Enter Topic Name:", placeholder="e.g., Quantum Entanglement, The French Revolution...")

st.markdown("### 3. Generate Magic")
if st.button("🚀 Refactor to Geek Notes"):
    prompt = ""
    gemini_file = None
    tmp_path = None
    
    with st.spinner("Processing input content..."):
        # Handle inputs
        if input_type == "YouTube Video Link" and yt_url:
            transcript, error = extract_yt_transcript(yt_url)
            if error:
                st.error(f"Error fetching transcript: {error}")
                st.stop()
            prompt = f"Please refactor the following YouTube video transcript into detailed notes:\n\n{transcript}"
                
        elif input_type == "Video File Upload" and uploaded_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name
            
            with st.spinner("Uploading video to Gemini (this may take a minute depending on size)..."):
                try:
                    gemini_file = genai.upload_file(path=tmp_path)
                    
                    # Wait for processing if needed (video processing can take time)
                    while gemini_file.state.name == "PROCESSING":
                        st.info("Gemini is processing the video...", icon="⏳")
                        time.sleep(5)
                        gemini_file = genai.get_file(gemini_file.name)
                        
                    if gemini_file.state.name == "FAILED":
                        st.error("Video processing failed.")
                        st.stop()
                        
                    prompt = "Please analyze the attached video lecture and generate detailed notes."
                except Exception as e:
                    st.error(f"Error uploading video: {e}")
                    st.stop()
            
        elif input_type == "Document Upload (PDF/DOCX/TXT)" and uploaded_file:
            file_ext = uploaded_file.name.split('.')[-1].lower()
            try:
                if file_ext == 'pdf':
                    extracted = extract_text_from_pdf(uploaded_file)
                elif file_ext == 'docx':
                    extracted = extract_text_from_docx(uploaded_file)
                elif file_ext == 'txt':
                    extracted = uploaded_file.read().decode('utf-8')
                prompt = f"Please refactor the following document content into detailed notes:\n\n{extracted}"
            except Exception as e:
                st.error(f"Error reading document: {e}")
                st.stop()
                
        elif input_type in ["Raw Transcript", "Topic Name Only"] and user_input_text:
            if input_type == "Topic Name Only":
                prompt = f"Please generate a comprehensive, detailed lecture-style breakdown and notes for the following topic:\n\n{user_input_text}"
            else:
                prompt = f"Please refactor the following transcript into detailed notes:\n\n{user_input_text}"
            
        if not prompt and not gemini_file:
            st.warning("⚠️ Please provide the required input before generating.")
        else:
            with st.spinner(f"Refactoring with {model_name}... 🧠"):
                try:
                    contents = [prompt]
                    if gemini_file:
                        contents = [gemini_file, prompt]
                    
                    # Initialize Model
                    try:
                        model = genai.GenerativeModel(
                            model_name=model_name,
                            system_instruction=SYSTEM_PROMPT,
                            generation_config=generation_config
                        )
                        response = model.generate_content(contents)
                    except Exception as fallback_e:
                        st.warning(f"Lite model failed: {fallback_e}. Failing back to standard gemini-2.5-flash.")
                        # Fallback to standard flash if lite fails
                        model = genai.GenerativeModel(
                            model_name="gemini-2.5-flash",
                            system_instruction=SYSTEM_PROMPT,
                            generation_config=generation_config
                        )
                        response = model.generate_content(contents)
                    
                    if response:
                        st.success("✨ Notes generated successfully!")
                        
                        cleaned_notes = clean_markdown(response.text)
                        
                        with st.expander("View Refactored Notes", expanded=True):
                            st.markdown(cleaned_notes)
                            
                        col1, col2 = st.columns(2)
                        with col1:
                            st.download_button(
                                label="📥 Download Notes as Markdown",
                                data=cleaned_notes,
                                file_name="refactored_notes.md",
                                mime="text/markdown"
                            )
                        with col2:
                            with st.spinner("Generating PDF..."):
                                pdf_bytes = generate_pdf(cleaned_notes)
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 Download Notes as PDF",
                                    data=pdf_bytes,
                                    file_name="refactored_notes.pdf",
                                    mime="application/pdf"
                                )
                            else:
                                st.error("Failed to generate PDF.")
                        
                except Exception as e:
                    st.error(f"Generation error: {e}")
                finally:
                    # Cleanup
                    if gemini_file:
                        try:
                            genai.delete_file(gemini_file.name)
                        except:
                            pass
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except:
                            pass
