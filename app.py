import streamlit as st
import google.generativeai as genai
import tempfile
import os
import time
from youtube_transcript_api import YouTubeTranscriptApi
import PyPDF2
import docx
import re
from fpdf import FPDF
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
with st.sidebar:
    st.header("🔑 API Settings")
    user_api_key = st.text_input(
        "Enter your Gemini API Key:",
        type="password",
        help="Get your API key from [Google AI Studio](https://aistudio.google.com/app/apikey)",
        placeholder="AIza..."
    )
    
    # Store in session state for persistence during the session
    if user_api_key:
        st.session_state.api_key = user_api_key
    
    st.divider()
    st.info("Your API key is only used for this session and is not stored permanently.")

# Initialize the API with the provided key (if any)
if "api_key" in st.session_state and st.session_state.api_key:
    genai.configure(api_key=st.session_state.api_key)
else:
    # We still need to call configure, but we'll handle the missing key during generation
    pass

# Load System Prompt
@st.cache_data
def load_system_prompt():
    # Try local path first, then relative path (for cloud deployment)
    prompt_paths = [
        r"system_prompt.md",
        "system_prompt.md",
        "../system_prompt.md"
    ]
    for path in prompt_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    
    st.error("System prompt file (system_prompt.md) not found in any expected location.")
    return "You are The Lecture Refactorer."

SYSTEM_PROMPT = load_system_prompt()

# Utility Functions
def clean_markdown(text):
    # Remove excessive newlines (more than 2 to just 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def generate_pdf(text):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Use standard fonts (Arial/Helvetica)
    pdf.set_font("Helvetica", size=12)
    
    # Simple header - Use 0 for full width to avoid margin issues
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(0, 10, txt="Lecture Notes", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Helvetica", size=11)
    
    # Clean up markdown for simple text PDF
    # Encode/Decode to handle potential UTF-8 characters that FPDF standard fonts might skip
    def sanitize_text(t):
        return t.encode('latin-1', 'replace').decode('latin-1')

    lines = text.split('\n')
    for line in lines:
        # Handle bold **text** and other markdown basics for a cleaner look
        clean_line = line.replace('**', '').replace('__', '').replace('#', '').strip()
        if clean_line:
            # Multi_cell handles word wrapping automatically
            # Using 0 for width to use the full printable width
            pdf.multi_cell(0, 7, txt=sanitize_text(clean_line))
        else:
            pdf.ln(4)
            
    return pdf.output(dest='S')

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
        elif "api_key" not in st.session_state or not st.session_state.api_key:
            st.error("🔑 Gemini API Key not found! Please enter your API key in the sidebar to proceed.")
            st.stop()
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
                        
                        st.divider()
                        st.subheader("📥 Export Options")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.download_button(
                                label="📥 Download as Markdown",
                                data=cleaned_notes,
                                file_name="refactored_notes.md",
                                mime="text/markdown",
                                key="download_md",
                                help="Download your notes as a standard Markdown file."
                            )
                        with col2:
                            with st.spinner("Preparing PDF..."):
                                pdf_bytes = generate_pdf(cleaned_notes)
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 Download as PDF",
                                    data=pdf_bytes,
                                    file_name="refactored_notes.pdf",
                                    mime="application/pdf",
                                    key="download_pdf",
                                    help="Download your notes as an elegant PDF document."
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
