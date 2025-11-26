import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
from PIL import Image
from fpdf import FPDF
import io
import re
import os
import json
import glob
import unicodedata
import tempfile
import base64
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure page title and icon
st.set_page_config(page_title="Ani-Gurumi AI", page_icon="🧶", layout="wide")

# --- ANALYTICS ---
try:
    if "UMAMI_SCRIPT_URL" in st.secrets and "UMAMI_WEBSITE_ID" in st.secrets:
        script_url = st.secrets["UMAMI_SCRIPT_URL"]
        website_id = st.secrets["UMAMI_WEBSITE_ID"]
        analytics_script = f'<script defer src="{script_url}" data-website-id="{website_id}"></script>'
        components.html(analytics_script, height=0, width=0)
except Exception:
    pass # Fail silently if secrets are missing or other errors occur

# Create folder for saved patterns if it doesn't exist
SAVE_DIR = "inventory"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

class PDF(FPDF):
    def header(self):
        if self.page_no() > 1: # No header on cover page
            self.set_font('Arial', 'I', 10)
            title = 'Ani-Gurumi AI - Crochet Pattern'
            try:
                title = title.encode('latin-1', 'replace').decode('latin-1')
            except:
                pass
            self.cell(0, 10, title, 0, 1, 'R')
            self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def cover_page(self, title, image_path=None):
        self.add_page()
        
        # Logo (small at top)
        if os.path.exists("logo.png"):
            try:
                # 30mm width, centered
                x_pos = (210 - 30) / 2
                self.image("logo.png", x=x_pos, y=10, w=30)
            except:
                pass

        self.set_font('Arial', 'B', 24)
        self.ln(30) # Move down (past logo)
        
        # Title
        try:
            safe_title = title.encode('latin-1', 'replace').decode('latin-1')
        except:
            safe_title = "Crochet Pattern"
        self.cell(0, 10, safe_title, 0, 1, 'C')
        self.ln(10)
        
        # Image
        if image_path:
            try:
                # Center image (A4 width 210mm)
                # Image width 70mm (smaller to fit tall images)
                x_pos = (210 - 70) / 2
                self.image(image_path, x=x_pos, w=70)
            except:
                pass
        
        self.ln(20)
        self.set_font('Arial', '', 14)
        self.cell(0, 10, "Created by Ani-Gurumi AI", 0, 1, 'C')
        self.add_page() # New page for text

def clean_text(text):
    """Removes emojis and replaces difficult characters for FPDF (latin-1)."""
    text = unicodedata.normalize('NFC', text)
    text = text.replace('**', '')
    text = text.replace('__', '')
    replacements = {'”': '"', '“': '"', '’': "'", '–': '-', '—': '-'}
    for k, v in replacements.items():
        text = text.replace(k, v)
    try:
        text = text.encode('latin-1', 'replace').decode('latin-1')
    except:
        pass
    return text

def create_pdf(text, image_file, title="Crochet Pattern"):
    pdf = PDF()
    
    # Handle image for cover page
    tmp_filename = None
    if image_file:
        try:
            img = Image.open(image_file)
            if img.mode in ("RGBA", "P"): 
                img = img.convert("RGB")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                img.save(tmp_file, format="JPEG")
                tmp_filename = tmp_file.name
        except:
            pass

    # Create cover page
    pdf.cover_page(title, tmp_filename)
    
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Parse text
    lines = text.split('\n')
    for line in lines:
        clean_line = clean_text(line).strip()
        if not clean_line:
            pdf.ln(5)
            continue
            
        if line.startswith('#'):
            level = len(line.split(' ')[0])
            content = clean_text(line.lstrip('#').strip())
            if level == 1:
                pdf.set_font("Arial", 'B', 16)
                pdf.ln(5)
                pdf.cell(0, 10, content, 0, 1, 'L')
                pdf.ln(2)
            elif level == 2:
                pdf.set_font("Arial", 'B', 14)
                pdf.ln(4)
                pdf.cell(0, 10, content, 0, 1, 'L')
            else:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 8, content, 0, 1, 'L')
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            pdf.set_font("Arial", '', 12)
            pdf.set_x(15) 
            pdf.multi_cell(0, 6, clean_line)
        elif re.match(r'^\d+\.', line.strip()):
            pdf.set_font("Arial", '', 12)
            pdf.set_x(15)
            pdf.multi_cell(0, 6, clean_line)
        else:
            pdf.set_font("Arial", '', 12)
            pdf.multi_cell(0, 6, clean_line)
            
            # Check for round counter
            counter_text = get_round_counter_text(clean_line)
            if counter_text:
                pdf.set_font("Courier", 'B', 12) # Monospace for alignment
                pdf.set_x(20) # Indent
                pdf.cell(0, 6, counter_text, 0, 1)
                pdf.ln(2)

    output = pdf.output(dest='S').encode('latin-1')
    
    # Clean up image
    if tmp_filename:
        try:
            os.unlink(tmp_filename)
        except:
            pass
            
    return output

def save_pattern_to_disk(name, pattern_data, image_file):
    """Saves pattern (JSON) and image to inventory."""
    # Create a safe filename
    safe_name = "".join([c for c in name if c.isalpha() or c.isdigit() or c==' ']).strip().replace(" ", "_")
    base_path = os.path.join(SAVE_DIR, safe_name)
    
    # Save JSON data
    with open(f"{base_path}.json", "w", encoding="utf-8") as f:
        json.dump(pattern_data, f, ensure_ascii=False, indent=2)
        
    # Save image (for PDF and display)
    if image_file:
        try:
            # If image_file is a string (path)
            if isinstance(image_file, str) and os.path.exists(image_file):
                 img = Image.open(image_file)
                 img.save(f"{base_path}.png")
            # If image_file is an UploadedFile (from Streamlit)
            elif hasattr(image_file, 'seek'):
                image_file.seek(0)
                img = Image.open(image_file)
                img.save(f"{base_path}.png")
        except Exception as e:
            print(f"Could not save image: {e}")

def load_saved_patterns():
    """Loads list of saved patterns from inventory."""
    files = glob.glob(os.path.join(SAVE_DIR, "*.json"))
    patterns = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = data.get("project_name", data.get("name", "Unnamed Project"))
                patterns.append({"name": name, "path": f, "base_path": f.replace(".json", "")})
        except:
            pass
    return patterns

def pattern_json_to_markdown(data):
    """Converts JSON pattern to Markdown text for PDF/Save."""
    md = f"# {data.get('project_name', 'Crochet Pattern')}\n\n"
    md += f"**Difficulty:** {data.get('difficulty', 'Unknown')}\n\n"
    
    md += "**Materials:**\n"
    for mat in data.get('materials', []):
        md += f"- {mat}\n"
    md += "\n"
    
    if data.get('hybrid_suggestion'):
        md += "**Hybrid Mode Suggestion:**\n"
        md += f"- Type: {data['hybrid_suggestion'].get('type')}\n"
        md += f"- Description: {data['hybrid_suggestion'].get('description')}\n\n"
        
    md += "## Pattern\n"
    for comp in data.get('components', []):
        md += f"### {comp.get('name', 'Part')}\n"
        for step in comp.get('steps', []):
            md += f"- {step}\n"
        md += "\n"
        
    return md

def get_round_counter_text(step_text):
    """
    Parses step text for round ranges and returns a plain text string of numbers.
    Returns None if no range found.
    """
    # Regex to find ranges like "Rnd 5-10", "Rnds 5-10", "Row 5-10", "R 5-10", "Varv 5-10", "R8-R14"
    # Case insensitive, handles optional spaces, dots, plurals, different separators, and repeated prefixes
    match = re.search(r'(?:Rnds?|Rows?|Rs?|Varv|Rounds?)\.?\s*(\d+)\s*(?:-|–|to)\s*(?:(?:Rnds?|Rows?|Rs?|Varv|Rounds?)\.?\s*)?(\d+)', step_text, re.IGNORECASE)
    
    if match:
        try:
            start = int(match.group(1))
            end = int(match.group(2))
            
            # Only generate if it's a valid range and not too huge
            if start < end and (end - start) < 50: 
                numbers = []
                count = 0
                for i in range(start, end + 1):
                    numbers.append(str(i))
                    count += 1
                    # Add separator every 5 numbers, but not at the very end
                    if count % 5 == 0 and i != end:
                        numbers.append("|")
                
                return " ".join(numbers)
        except:
            pass
    return None

def generate_round_counter(step_text):
    """
    Returns formatted HTML string for the UI round counter.
    """
    text = get_round_counter_text(step_text)
    if text:
        # Add extra spacing for HTML display
        formatted_str = text.replace(" ", "&nbsp;&nbsp;")
        
        return f"""
        <div style="
            margin-left: 20px; 
            margin-bottom: 10px; 
            font-family: monospace; 
            color: #00e5ff; 
            font-weight: bold;
            font-size: 1.1em;
        ">
            {formatted_str}
        </div>
        """
    return None

def render_interactive_pattern(data):
    """Renders the pattern as an interactive Quest Log."""
    st.markdown(f"## 🛡️ Quest: {data.get('project_name', 'Unknown Project')}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Difficulty:** {data.get('difficulty', 'Unknown')}")
    with col2:
        st.warning(f"**Materials:** {', '.join(data.get('materials', []))}")
        
    if data.get('hybrid_suggestion'):
        with st.expander("🖨️ Hybrid Mode Suggestion", expanded=True):
            st.write(f"**Part:** {data['hybrid_suggestion'].get('type')}")
            st.write(f"**Info:** {data['hybrid_suggestion'].get('description')}")
            
            # Hybrid Link (Thingiverse)
            search_term = data['hybrid_suggestion'].get('search_term')
            if search_term:
                url = f"https://www.thingiverse.com/search?q={search_term}&type=things&sort=relevant"
                st.link_button("🔍 Find STL on Thingiverse", url)
    
    st.markdown("### 📜 Pattern (Quest Steps)")
    
    # Loop through components (Head, Body, etc.)
    for i, comp in enumerate(data.get('components', [])):
        # Use expander for each part
        with st.expander(f"🧶 {comp.get('name', 'Part')}", expanded=False):
            # Checkboxes for each round
            for j, step in enumerate(comp.get('steps', [])):
                st.checkbox(step, key=f"step_{i}_{j}")
                
                # Round Counter Logic
                counter_html = generate_round_counter(step)
                if counter_html:
                    st.markdown(counter_html, unsafe_allow_html=True)
    
    st.success("Don't forget to check off steps as you go! ✅")

def main():
    # --- SIDEBAR ---
    
    # Show logo in sidebar (Moved to top)
    if os.path.exists("logo.png"):
        with open("logo.png", "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        # Use components.html to isolate JS/CSS and ensure functionality
        with st.sidebar:
            components.html(
                f"""
                <!DOCTYPE html>
                <html>
                <head>
                <style>
                    body {{
                        margin: 0;
                        padding: 0;
                        background-color: transparent;
                        display: flex;
                        justify-content: center;
                        align-items: flex-end; /* Image at bottom */
                        height: 100%;
                        overflow: hidden;
                        font-family: sans-serif;
                    }}
                    .logo-container {{
                        position: relative;
                        width: 100%;
                        text-align: center;
                        padding-top: 50px; /* Space for bubble */
                        padding-bottom: 10px;
                    }}
                    img {{
                        width: 100%;
                        max-width: 180px;
                        cursor: pointer;
                        filter: drop-shadow(0px 4px 6px rgba(0,0,0,0.1));
                        transition: transform 0.1s;
                    }}
                    img:active {{
                        transform: scale(0.95);
                    }}
                    
                    /* Speech Bubble */
                    .speech-bubble {{
                        position: absolute;
                        top: 0px; /* Top of container */
                        left: 50%;
                        transform: translateX(-50%);
                        background-color: #ffffff;
                        color: #000000;
                        padding: 15px;
                        border-radius: 15px;
                        font-size: 14px;
                        font-weight: bold;
                        width: 160px;
                        display: none;
                        box-shadow: 0px 4px 15px rgba(0,0,0,0.2);
                        border: 2px solid #2b313e;
                        text-align: center;
                        z-index: 1000;
                        opacity: 0;
                        transition: opacity 0.3s ease;
                    }}
                    
                    .speech-bubble.show {{
                        display: block;
                        opacity: 1;
                    }}
                    
                    .speech-bubble::after {{
                        content: '';
                        position: absolute;
                        bottom: -10px;
                        left: 50%;
                        transform: translateX(-50%);
                        border-width: 10px 10px 0;
                        border-style: solid;
                        border-color: #ffffff transparent transparent transparent;
                    }}
                </style>
                </head>
                <body>
                    <div class="logo-container">
                        <div id="speech-bubble" class="speech-bubble"></div>
                        <img id="mascot-img" src="data:image/png;base64,{data}" onclick="interact()">
                    </div>
                    <script>
                        let timeoutId = null;
                        
                        function interact() {{
                            const messages = [
                                // Intro
                                "Hi! I'm Anigurobo! 🤖",
                                "Ready to crochet? 🧶",
                                "I love Amigurumi! ❤️",
                                "Need help? I'm here!",
                                
                                // Tips
                                "Tip: Use a stitch marker to keep track of rounds! 📍",
                                "Tip: Don't crochet too tight, your hands will thank you! ✋",
                                "Tip: For Amigurumi, use a smaller hook than recommended to avoid holes. 🕳️",
                                "Tip: Count your stitches carefully! 1, 2, 3... 🔢",
                                "Tip: Listen to anime OSTs while crocheting for extra power! 🎵",
                                "Tip: Don't forget to weave in your ends! 🪡",
                                "Tip: Magic Ring is tricky at first, but don't give up! ✨",
                                "Tip: Invisible decrease looks much neater for Amigurumi. 👻",
                                "Tip: Stuff your Amigurumi firmly, but don't overstuff! 🧸",
                                "Tip: Use safety eyes for a professional look (but not for babies!). 👀",
                                "Tip: Yarn under instead of yarn over for tighter stitches (X-stitch). ❌",
                                "Tip: Take breaks and stretch your wrists! 🧘",
                                "Tip: Keep a crochet journal to track your projects. 📓",
                                "Tip: Crochet in a spiral, don't join rounds unless told to. 🌀",
                                "Tip: Use pins to position parts before sewing them on. 📍",
                                "Tip: Daylight is the best light for crocheting dark yarn. ☀️",
                                "Tip: A bent tip tapestry needle makes sewing easier. 🪡",
                                
                                // Jokes (Anime & Crochet)
                                "Why was the yarn sad? It lost its thread... 😢",
                                "What did one needle say to the other? We're hooked! 👯",
                                "Why does Naruto like crochet? He's a master of 'Shadow Clone Stitching'! 🍥",
                                "I tried to crochet a Pokémon, but it ran away... Gotta catch 'em all! ⚡",
                                "What do you call a crocheted Saiyan? Super-Yarn-jin! 🔥",
                                "Did you hear about the crocheter who got arrested? She was caught red-handed! 🚓",
                                "Why are crocheters good at anime? We can follow the plot thread! 📺",
                                "What is a crocheter's favorite movie? The Lord of the Strings! 💍",
                                "What did Yoda say about crochet? 'Do or do not, there is no try... to count stitches.' 🌌",
                                "Why did the Titan eat yarn? He wanted a high-fiber diet! 🧱",
                                "How does a crocheter fight? With a hook and loop! 🥊",
                                "What's a ghost's favorite stitch? The boo-ble stitch! 👻",
                                "Why is One Piece like a yarn stash? It never ends! 🏴‍☠️",
                                "What do you call a cat who crochets? A purr-l stitcher! 🐱",
                                "Why did the crochet hook break up with the yarn? It was too clingy! 💔",
                                "What's a crocheter's favorite anime genre? Slice of Life (and yarn)! 🍰",
                                "Why did the scarecrow win an award? He was outstanding in his field (of crochet)! 🌾",
                                "Knitting is okay, but crochet is cooler. It's just one hook to rule them all! 💍",
                                "My yarn stash isn't a mess, it's a dragon's hoard! 🐉"
                            ];
                            
                            var b = document.getElementById("speech-bubble");
                            
                            if (b) {{
                                // Clear previous timer so message doesn't disappear too fast
                                if (timeoutId) {{
                                    clearTimeout(timeoutId);
                                }}
                                
                                const msg = messages[Math.floor(Math.random() * messages.length)];
                                b.innerText = msg;
                                b.classList.add("show");
                                
                                // Calculate time based on text length (min 5s + 50ms per char)
                                const duration = 5000 + (msg.length * 50);
                                
                                timeoutId = setTimeout(() => {{
                                    b.classList.remove("show");
                                }}, duration);
                            }}
                        }}
                    </script>
                </body>
                </html>
                """,
                height=350, 
                scrolling=False
            )

    st.sidebar.title("Settings ⚙️")
    
    # API Key Management
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except FileNotFoundError:
        # Fallback for local development without secrets.toml (optional, but good for safety)
        api_key = os.getenv("GOOGLE_API_KEY")
        
    if not api_key:
        st.sidebar.error("⚠️ Missing API Key")
        st.sidebar.info("Please add `GEMINI_API_KEY` to your Streamlit secrets.")
        st.stop()

    # Model Selection (Hardcoded)
    selected_model_name = "gemini-2.0-flash"

    # Inventory System (Load)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📂 My Inventory")
    saved_patterns = load_saved_patterns()
    
    selected_inventory_item = st.sidebar.selectbox(
        "Select Project:", 
        ["-- Select --"] + [p["name"] for p in saved_patterns]
    )
    
    if st.sidebar.button("Load Project 📥"):
        if selected_inventory_item != "-- Select --":
            # Find correct file
            pattern_info = next((p for p in saved_patterns if p["name"] == selected_inventory_item), None)
            if pattern_info:
                try:
                    with open(pattern_info["path"], "r", encoding="utf-8") as f:
                        data = json.load(f)
                        st.session_state['pattern_data'] = data
                        # Create markdown for PDF export
                        st.session_state['generated_pattern'] = pattern_json_to_markdown(data)
                        
                        # Restore progress (checkboxes)
                        if 'progress' in data:
                            for key, value in data['progress'].items():
                                st.session_state[key] = value
                        
                        # Load image to session state if it exists
                        img_path = pattern_info["base_path"] + ".png"
                        if os.path.exists(img_path):
                            st.session_state['loaded_image_path'] = img_path
                        else:
                             if 'loaded_image_path' in st.session_state:
                                 del st.session_state['loaded_image_path']
                                 
                    st.success(f"Loaded {selected_inventory_item}!")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Could not load: {e}")

    # --- MAIN CONTENT ---
    
    # Custom CSS for nicer UI
    st.markdown("""
    <style>
        /* Set dark background on entire app */
        .stApp {
            background-color: #0e1117;
        }
        
        /* Darker sidebar */
        [data-testid="stSidebar"] {
            background-color: #1a1c24;
        }
        
        /* Remove top padding so banner sits flush */
        .block-container {
            padding-top: 0rem;
            padding-bottom: 0rem;
            margin-top: 0rem;
        }
        
        /* Dark blue background for logo */
        .logo-container {
            background-color: #0e1117;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            text-align: center;
            border: 2px solid #2b313e;
        }
        
        /* Disable fullscreen on logo - BUT allow pointer events for click */
        .logo-container img {
            /* pointer-events: none;  <-- Removed to allow click */
        }

        .main-header {
            font-size: 3rem;
            font-weight: bold;
            color: #FF4B4B;
            text-align: center;
            margin-bottom: 0;
            text-shadow: 2px 2px 4px #000000;
        }
        .sub-header {
            font-size: 1.2rem;
            color: #888;
            text-align: center;
            margin-bottom: 2rem;
        }
        /* Make sidebar text lighter */
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {
            color: #ffffff;
        }
        /* Make all text lighter */
        p, h1, h2, h3, label {
            color: #ffffff;
        }
    </style>
    """, unsafe_allow_html=True)

    # Banner
    if os.path.exists("banner.png"):
        st.image("banner.png", use_container_width=True)
    
    st.markdown('<p class="main-header">Ani-Gurumi AI 🧶✨</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Your personal AI assistant for creating magical crochet patterns from anime images.</p>', unsafe_allow_html=True)

    # --- NEW GENERATION ---
    st.markdown("---")
    
    col1, col2 = st.columns([1, 1], gap="large")
    
    with col1:
        st.markdown("### 1. Upload Image 🖼️")
        
        tab1, tab2 = st.tabs(["Upload Image 📁", "Take Photo 📸"])
        
        uploaded_file = None
        
        with tab1:
            file_upload = st.file_uploader("Choose an image (JPG/PNG)", type=["jpg", "jpeg", "png"])
            if file_upload:
                uploaded_file = file_upload
        
        with tab2:
            enable_camera = st.checkbox("Enable Camera")
            if enable_camera:
                camera_photo = st.camera_input("Take a picture")
                if camera_photo:
                    uploaded_file = camera_photo
        
        # Show uploaded image OR loaded image from inventory
        if uploaded_file:
            image = Image.open(uploaded_file)
            st.image(image, caption='Your selected character', use_container_width=True)
        elif 'loaded_image_path' in st.session_state and os.path.exists(st.session_state['loaded_image_path']):
            image = Image.open(st.session_state['loaded_image_path'])
            st.image(image, caption='Loaded character', use_container_width=True)
            uploaded_file = st.session_state['loaded_image_path'] # For PDF export

    with col2:
        st.markdown("### 2. Configuration ⚙️")
        
        # Fill in name if we loaded a project
        default_name = ""
        if 'pattern_data' in st.session_state and st.session_state['pattern_data']:
            default_name = st.session_state['pattern_data'].get("project_name", "")
            
        pattern_name_input = st.text_input("Character Name (for saving)", value=default_name, placeholder="E.g. Naruto Uzumaki")
        
        st.markdown("#### Advanced")
        hybrid_mode = st.checkbox("Hybrid Mode 🖨️", value=False, help="If enabled: AI suggests 3D-printed parts for complex details.")
        if hybrid_mode:
            st.info("💡 **Hybrid Mode:** Perfect if you have a 3D printer! You get suggestions for parts to print (eyes, weapons) instead of crocheting everything.")
        
        st.markdown("### 3. Create! ✨")
        generate_btn = st.button("Generate Pattern 🪄", type="primary", use_container_width=True)

    if uploaded_file is not None and generate_btn:
        if not api_key:
            st.error("⚠️ You must provide a Google API Key in the settings menu.")
            return

        with st.spinner('🧶 AI is analyzing the image and crocheting a pattern...'):
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(selected_model_name, generation_config={"response_mime_type": "application/json"})

                    base_prompt = """
                    You are an expert at creating Amigurumi crochet patterns.
                    Analyze the image and create a detailed pattern in ENGLISH.
                    
                    You MUST respond with a strict JSON object following this structure:
                    {
                      "project_name": "Character Name",
                      "difficulty": "Easy/Medium/Hard",
                      "materials": ["Yarn Color A", "Hook Size", "Safety Eyes"],
                      "hybrid_suggestion": {"type": "E.g. Eyes/Weapon", "description": "Description of what can be 3D printed", "search_term": "Thingiverse search term optimized for Amigurumi. Include 'crochet', 'safety eyes', or 'amigurumi' (e.g. 'Anime safety eyes crochet' or 'Naruto headband for amigurumi')"} (Leave empty/null if not hybrid),
                      "components": [
                        {
                          "name": "Head",
                          "steps": ["R1: 6 sc in MR", "R2: Inc (12)", "R3: ..."]
                        },
                        {
                          "name": "Body",
                          "steps": ["..."]
                        }
                      ]
                    }

                    **TERMINOLOGY (use in steps):**
                    - sc = single crochet
                    - inc = increase
                    - dec = decrease
                    - MR = Magic Ring
                    
                    **IMPORTANT RULES:**
                    1. **ORIENTATION:** For EACH component, you MUST specify the direction.
                       - Example: "Head (Worked top-down. MR is the top)."
                       - If sewing is needed, write: "Leave a long tail for sewing."
                    2. **LANDMARKS:** For the Head, you MUST specify where to place safety eyes.
                       - Example: "Tip: Insert safety eyes between R10 and R11, 6 stitches apart."
                    3. **ASSEMBLY:** Be specific about placement.
                       - Example: "Sew the body (neck opening) to the bottom of the head (R20)."
                    4. **COLOR RULES:**
                       - **START COLOR:** The FIRST instruction for EVERY component MUST specify the color.
                         - Example: "Start with SKIN COLOR yarn."
                       - **COLOR CHANGES:** If color changes, write it as a separate step.
                         - Example: "Change to BLACK yarn."
                       - **SPECIFICITY:** Use descriptive names based on the image (e.g., "Dark Blue", "Lime Green"), not just "Color A".
                    - ch = chain
                    - sl st = slip stitch
                    - R = Round
                    """

                    if hybrid_mode:
                        base_prompt += "\n**HYBRID MODE:** Fill 'hybrid_suggestion' with suggestions for 3D printed parts."
                    else:
                        base_prompt += "\n**ALL CROCHET:** Leave 'hybrid_suggestion' empty/null."

                    # Load image object if it is a path (from inventory)
                    img_to_send = image
                    if isinstance(uploaded_file, str):
                         img_to_send = Image.open(uploaded_file)

                    response = model.generate_content([base_prompt, img_to_send])
                    
                    # Try parsing JSON
                    try:
                        pattern_data = json.loads(response.text)
                        st.session_state['pattern_data'] = pattern_data
                        # Convert to text for backward compatibility/saving
                        st.session_state['generated_pattern'] = pattern_json_to_markdown(pattern_data)
                    except json.JSONDecodeError:
                        # Fallback if AI fails JSON
                        st.error("Could not parse AI response as JSON. Showing raw text.")
                        st.session_state['generated_pattern'] = response.text
                        st.session_state['pattern_data'] = None
                    
                except Exception as e:
                    st.error(f"Error: {e}")
                    if "429" in str(e):
                        st.warning("Quota exceeded. Change model.")

    # Show result (from session state)
    if 'pattern_data' in st.session_state and st.session_state['pattern_data']:
        st.success("Done! 🧶")
        st.markdown("---")
        
        # Render interactively
        render_interactive_pattern(st.session_state['pattern_data'])
        
        # --- PATTERN EDITING ---
        st.markdown("---")
        st.markdown("### ✍️ Edit Pattern")
        
        edit_instruction = st.chat_input("Do you want to change something in the pattern? (e.g. 'Make the arms longer')")
        
        if edit_instruction:
            if not api_key:
                 st.error("⚠️ Missing API Key")
                 st.stop()
                 
            with st.spinner("🧶 Anigurobo is adjusting the pattern..."):
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(selected_model_name, generation_config={"response_mime_type": "application/json"})
                    
                    current_pattern = json.dumps(st.session_state['pattern_data'])
                    
                    edit_prompt = f"""
                    You are an expert Amigurumi pattern editor.
                    
                    Current Pattern (JSON):
                    {current_pattern}
                    
                    User Request: "{edit_instruction}"
                    
                    INSTRUCTIONS:
                    1. Update the JSON data based on the user's request.
                    2. Keep the structure EXACTLY the same (keys: project_name, difficulty, materials, hybrid_suggestion, components).
                    3. Only change what is requested.
                    4. Output the valid JSON object.
                    
                    **REMEMBER THE RULES:**
                    - **ORIENTATION:** Specify direction (e.g., top-down) and sewing tails.
                    - **LANDMARKS:** Specify eye placement (e.g., between R10-11).
                    - **ASSEMBLY:** Be specific about alignment.
                    - **COLORS:** Mention start colors and specific color names.
                    """
                    
                    response = model.generate_content(edit_prompt)
                    
                    new_pattern_data = json.loads(response.text)
                    st.session_state['pattern_data'] = new_pattern_data
                    st.session_state['generated_pattern'] = pattern_json_to_markdown(new_pattern_data)
                    
                    st.success("Pattern updated!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Failed to update pattern: {e}")

        st.markdown("### 💾 Save & Export")
        
        col_save, col_pdf = st.columns(2)
        
        with col_save:
            if st.button("Save to Inventory 📥"):
                if pattern_name_input:
                    # Update name in data if user changed it
                    st.session_state['pattern_data']['project_name'] = pattern_name_input
                    
                    # Save progress (which boxes are checked)
                    progress_state = {}
                    if 'pattern_data' in st.session_state:
                        for i, comp in enumerate(st.session_state['pattern_data'].get('components', [])):
                            for j, step in enumerate(comp.get('steps', [])):
                                key = f"step_{i}_{j}"
                                if key in st.session_state:
                                    progress_state[key] = st.session_state[key]
                    st.session_state['pattern_data']['progress'] = progress_state

                    save_pattern_to_disk(pattern_name_input, st.session_state['pattern_data'], uploaded_file)
                    st.success("Saved to Inventory!")
                else:
                    st.error("You must give the character a name!")

        with col_pdf:
            try:
                # Ensure we have markdown for PDF
                if 'generated_pattern' not in st.session_state:
                     st.session_state['generated_pattern'] = pattern_json_to_markdown(st.session_state['pattern_data'])
                
                pdf_bytes = create_pdf(st.session_state['generated_pattern'], uploaded_file, title=pattern_name_input or "Crochet Pattern")
                
                # Create filename
                download_name = "ani-gurumi.pdf"
                if pattern_name_input:
                    clean_name = "".join([c for c in pattern_name_input if c.isalpha() or c.isdigit() or c==' ']).strip().replace(" ", "_")
                    if clean_name:
                        download_name = f"{clean_name} Ani-gurumi.pdf"

                st.download_button(
                    label="Download PDF 📄",
                    data=pdf_bytes,
                    file_name=download_name,
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"PDF Error: {e}")

if __name__ == "__main__":
    main()
