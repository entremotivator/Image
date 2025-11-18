import streamlit as st
import json
import requests
import time
import base64
from io import BytesIO
from PIL import Image
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import os

# Google Drive API Configuration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CLIENT_CONFIG = {
    "web": {
        "client_id": st.secrets.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": st.secrets.get("GOOGLE_CLIENT_SECRET", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [st.secrets.get("REDIRECT_URI", "http://localhost:8501")]
    }
}

# Prompt Library with 100 prompts
PROMPT_LIBRARY = {
    "E-commerce Mockups": [
        "Create a professional t-shirt mockup with this logo on a white background",
        "Design a hoodie mockup featuring this design on a model in urban setting",
        "Generate a coffee mug mockup with this artwork in a cozy cafe scene",
        "Create a tote bag mockup with this design hanging on a white wall",
        "Design a phone case mockup with this pattern on iPhone 15 Pro",
        "Generate a water bottle mockup with this branding on a gym background",
        "Create a baseball cap mockup with this logo embroidered on front",
        "Design a poster mockup with this art hanging in modern living room",
        "Generate a business card mockup with this design on marble surface",
        "Create a notebook mockup with this cover design on wooden desk",
        "Design a packaging box mockup with this label in professional studio",
        "Generate a canvas print mockup with this artwork in gallery setting",
        "Create a laptop sticker mockup with this design on MacBook Pro",
        "Design a shopping bag mockup with this branding in retail store",
        "Generate a pillow mockup with this pattern on modern sofa",
        "Create a banner mockup with this design hanging in outdoor event",
        "Design a label mockup with this artwork on wine bottle",
        "Generate a book cover mockup with this design in bookstore display",
        "Create a greeting card mockup with this illustration on elegant surface",
        "Design a keychain mockup with this logo in lifestyle flatlay",
        "Generate a skateboard deck mockup with this art in skate park",
        "Create a yoga mat mockup with this pattern in fitness studio",
        "Design a backpack mockup with this emblem on adventure background",
        "Generate a snapback hat mockup with this patch in street style scene",
        "Create a ceramic plate mockup with this design in restaurant setting"
    ],
    "Backgrounds": [
        "Replace background with professional white studio backdrop",
        "Change background to modern minimalist office environment",
        "Transform background into vibrant sunset beach scene",
        "Replace with elegant marble texture background",
        "Change to urban city street with bokeh lights at night",
        "Transform background into lush green forest landscape",
        "Replace with gradient pastel color fade background",
        "Change to rustic wooden planks texture",
        "Transform background into futuristic neon cyberpunk cityscape",
        "Replace with soft focus nature bokeh background",
        "Change to clean white brick wall texture",
        "Transform background into cozy coffee shop interior",
        "Replace with dramatic dark storm clouds",
        "Change to colorful abstract geometric patterns",
        "Transform background into snowy mountain landscape",
        "Replace with luxurious gold and black gradient",
        "Change to vibrant tropical paradise with palm trees",
        "Transform background into industrial concrete warehouse",
        "Replace with dreamy clouds in pastel sky",
        "Change to elegant black velvet texture",
        "Transform background into cherry blossom garden",
        "Replace with modern glass building reflections",
        "Change to desert sand dunes at golden hour",
        "Transform background into underwater ocean scene with rays of light",
        "Replace with cosmic space with stars and nebula"
    ],
    "Image Edits": [
        "Make the image more vibrant and saturated with bold colors",
        "Convert to black and white with high contrast",
        "Add dramatic cinematic lighting with lens flare",
        "Apply vintage film grain and faded colors effect",
        "Enhance details and sharpness for professional look",
        "Add realistic motion blur for dynamic movement",
        "Apply soft focus dreamy aesthetic with glow",
        "Transform into watercolor painting style",
        "Add dramatic shadows and highlights for depth",
        "Convert to pencil sketch with fine details",
        "Apply neon glow effects with vibrant edges",
        "Transform into oil painting with visible brushstrokes",
        "Add golden hour warm lighting and sun rays",
        "Apply tilt-shift miniature effect with selective focus",
        "Transform into pop art style with bold outlines",
        "Add rain and wet surface reflections",
        "Apply HDR effect with enhanced dynamic range",
        "Transform into anime/manga illustration style",
        "Add fog and atmospheric haze for mood",
        "Apply retro 80s vaporwave aesthetic with pink and purple",
        "Transform into vector art with flat colors",
        "Add lens bokeh and depth of field blur",
        "Apply cross-processing effect with shifted colors",
        "Transform into mosaic made of small tiles",
        "Add sparkles and magical light particles"
    ],
    "Professional Position Changes": [
        "Move subject to center of frame with rule of thirds composition",
        "Reposition person to left side with more negative space on right",
        "Move product to upper third of image for visual hierarchy",
        "Shift subject closer to camera for more intimate perspective",
        "Reposition elements using golden ratio composition",
        "Move person to right side with leading lines directing to them",
        "Center subject vertically and horizontally for symmetrical balance",
        "Shift product to lower portion with sky taking upper two-thirds",
        "Reposition subject off-center following diagonal composition",
        "Move person higher in frame to show more environmental context",
        "Shift product to corner for dynamic asymmetrical composition",
        "Reposition subject with more headroom for professional portrait",
        "Move elements to create triangular composition",
        "Shift person to foreground with background elements smaller",
        "Reposition product at eye level for natural viewing angle",
        "Move subject following S-curve composition through frame",
        "Shift elements to create leading lines toward focal point",
        "Reposition person with more breathing room in direction of gaze",
        "Move product to sweet spot intersection of rule of thirds grid",
        "Shift subject lower in frame for powerful upward perspective",
        "Reposition elements in frame within frame composition",
        "Move person to create dynamic diagonal line across image",
        "Shift product with negative space balancing visual weight",
        "Reposition subject at horizon line for landscape orientation",
        "Move elements to create radial composition emanating from center"
    ]
}

# API Configuration
API_BASE = "https://api.aiquickdraw.com"
API_KEY = st.secrets.get("API_KEY", "")

def init_session_state():
    """Initialize all session state variables"""
    defaults = {
        'google_auth_flow': None,
        'credentials': None,
        'drive_service': None,
        'tasks': [],
        'current_task_id': None,
        'selected_image_url': None,
        'selected_image_for_edit': None,
        'use_library_image': False,
        'selected_prompt_for_generation': None,
        'library_images': [],
        'search_query': '',
        'sort_by': 'Newest First',
        'filter_type': 'All',
        'view_mode': 'Grid',
        'custom_prompts': {cat: [] for cat in PROMPT_LIBRARY.keys()}
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def get_drive_service():
    """Get Google Drive service instance"""
    if st.session_state.credentials is None:
        return None
    
    return build('drive', 'v3', credentials=st.session_state.credentials)

def upload_to_gdrive(image_bytes, filename):
    """Upload image to Google Drive and make it public"""
    try:
        service = get_drive_service()
        if not service:
            st.error("Google Drive not connected")
            return None
        
        file_metadata = {'name': filename}
        media = MediaIoBaseUpload(BytesIO(image_bytes), mimetype='image/png', resumable=True)
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink, webContentLink'
        ).execute()
        
        file_id = file.get('id')
        
        # Make file public
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        # Generate direct public image URL
        public_image_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        
        return {
            'file_id': file_id,
            'web_view_link': file.get('webViewLink'),
            'web_content_link': file.get('webContentLink'),
            'public_image_url': public_image_url
        }
    except Exception as e:
        st.error(f"Upload failed: {str(e)}")
        return None

def list_drive_images():
    """List all images from Google Drive"""
    try:
        service = get_drive_service()
        if not service:
            return []
        
        results = service.files().list(
            q="mimeType contains 'image/'",
            fields="files(id, name, webViewLink, webContentLink, createdTime, size, mimeType, description)",
            orderBy="createdTime desc"
        ).execute()
        
        files = results.get('files', [])
        
        # Add public URLs
        for file in files:
            file_id = file.get('id')
            file['public_image_url'] = f"https://drive.google.com/uc?export=view&id={file_id}"
            file['thumbnail_url'] = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
            file['direct_link'] = f"https://lh3.googleusercontent.com/d/{file_id}"
            
            # Parse description to get original URL if available
            description = file.get('description', '')
            if description:
                try:
                    desc_data = json.loads(description)
                    file['original_url'] = desc_data.get('original_url')
                except:
                    pass
        
        return files
    except Exception as e:
        st.error(f"Failed to list images: {str(e)}")
        return []

def delete_drive_file(file_id):
    """Delete a file from Google Drive"""
    try:
        service = get_drive_service()
        if not service:
            return False
        
        service.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        st.error(f"Delete failed: {str(e)}")
        return False

def create_task(model, params):
    """Create a new image generation task"""
    url = f"{API_BASE}/open/task/create"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": params
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        if result.get('code') == 200:
            return result.get('data', {}).get('taskId')
    return None

def query_task(task_id):
    """Query task status"""
    url = f"{API_BASE}/open/task/query"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {"taskId": task_id}
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        if result.get('code') == 200:
            return result.get('data')
    return None

def wait_for_task(task_id, progress_bar=None, status_text=None):
    """Wait for task completion"""
    max_attempts = 60
    attempt = 0
    
    while attempt < max_attempts:
        task_data = query_task(task_id)
        
        if task_data:
            state = task_data.get('state')
            
            if progress_bar and status_text:
                progress = min((attempt + 1) / max_attempts, 0.95)
                progress_bar.progress(progress)
                status_text.text(f"Status: {state}")
            
            if state == 'success':
                if progress_bar:
                    progress_bar.progress(1.0)
                return task_data
            elif state == 'failed':
                return None
        
        time.sleep(2)
        attempt += 1
    
    return None

def download_image(url):
    """Download image from URL"""
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        st.error(f"Download failed: {str(e)}")
        return None

def google_auth_component():
    """Handle Google OAuth authentication"""
    st.subheader("🔐 Google Drive Connection")
    
    if st.session_state.credentials is None:
        if st.button("Connect Google Drive", type="primary"):
            try:
                flow = Flow.from_client_config(
                    CLIENT_CONFIG,
                    scopes=SCOPES,
                    redirect_uri=CLIENT_CONFIG['web']['redirect_uris'][0]
                )
                
                auth_url, _ = flow.authorization_url(prompt='consent')
                st.session_state.google_auth_flow = flow
                
                st.markdown(f"[Click here to authorize]({auth_url})")
                st.info("After authorizing, paste the redirect URL here:")
                
                redirect_response = st.text_input("Redirect URL")
                
                if redirect_response:
                    flow.fetch_token(authorization_response=redirect_response)
                    st.session_state.credentials = flow.credentials
                    st.session_state.drive_service = get_drive_service()
                    st.success("✅ Connected to Google Drive!")
                    st.rerun()
            except Exception as e:
                st.error(f"Authentication failed: {str(e)}")
    else:
        st.success("✅ Connected to Google Drive")
        if st.button("Disconnect"):
            st.session_state.credentials = None
            st.session_state.drive_service = None
            st.rerun()

def prompt_library_selector(default_category=None):
    """Display prompt library selector"""
    with st.expander("📚 Prompt Library", expanded=False):
        col1, col2 = st.columns([1, 3])
        
        with col1:
            categories = list(PROMPT_LIBRARY.keys())
            if default_category and default_category in categories:
                default_index = categories.index(default_category)
            else:
                default_index = 0
            
            category = st.selectbox(
                "Category",
                categories,
                index=default_index,
                key=f"prompt_cat_{default_category}"
            )
        
        with col2:
            # Combine built-in and custom prompts
            all_prompts = PROMPT_LIBRARY[category] + st.session_state.custom_prompts.get(category, [])
            
            if all_prompts:
                selected_prompt = st.selectbox(
                    "Select Prompt",
                    ["-- Choose a prompt --"] + all_prompts,
                    key=f"prompt_sel_{default_category}"
                )
                
                if selected_prompt != "-- Choose a prompt --":
                    if st.button("Use This Prompt", key=f"use_prompt_{default_category}"):
                        return selected_prompt
        
        st.markdown("**Tip:** Visit the Prompt Library page to add custom prompts!")
    
    return None

# Initialize session state
init_session_state()

# Main App
st.title("🎨 AI Image Generator with Google Drive")

# Sidebar
with st.sidebar:
    google_auth_component()
    
    st.markdown("---")
    st.markdown("### Navigation")
    page = st.radio(
        "Go to",
        ["Generate", "Upload Images", "History", "Library", "Prompt Library"],
        label_visibility="collapsed"
    )

# Page: Generate
if page == "Generate":
    st.header("Generate Images")
    
    tab1, tab2, tab3 = st.tabs(["Text-to-Image", "Image Edit (Qwen)", "Image Edit (Seedream)"])
    
    # Tab 1: Text-to-Image
    with tab1:
        st.subheader("Text-to-Image Generation")
        
        # Prompt library selector
        selected_prompt = prompt_library_selector()
        if selected_prompt:
            st.session_state.selected_prompt_for_generation = selected_prompt
            st.rerun()
        
        default_prompt = st.session_state.get('selected_prompt_for_generation', 
                                              "A photorealistic image of a majestic lion wearing a crown, digital art, highly detailed")
        prompt = st.text_area("Prompt", default_prompt)
        negative_prompt = st.text_area("Negative Prompt (Optional)", "blurry, low quality, bad anatomy")
        
        image_size = st.selectbox("Image Size", ["square_hd", "portrait_16_9", "landscape_16_9"])
        
        if st.button("Generate Image", type="primary"):
            if not prompt:
                st.warning("Please enter a prompt")
            else:
                with st.spinner("Creating task..."):
                    task_id = create_task("bytedance/flux-dev", {
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "image_size": image_size,
                        "num_images": 1
                    })
                
                if task_id:
                    st.info(f"Task ID: {task_id}")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    result = wait_for_task(task_id, progress_bar, status_text)
                    
                    if result:
                        result_json = json.loads(result.get('resultJson', '{}'))
                        result_urls = result_json.get('resultUrls', [])
                        
                        if result_urls:
                            st.success("✅ Generation complete!")
                            
                            for idx, img_url in enumerate(result_urls):
                                st.image(img_url, caption=f"Generated Image {idx+1}", use_container_width=True)
                                
                                # Download and upload to Drive
                                if st.session_state.credentials:
                                    with st.spinner("Uploading to Google Drive..."):
                                        img_bytes = download_image(img_url)
                                        if img_bytes:
                                            filename = f"generated_{task_id}_{idx}.png"
                                            drive_result = upload_to_gdrive(img_bytes, filename)
                                            
                                            if drive_result:
                                                st.success(f"✅ Uploaded to Drive: {filename}")
                                                
                                                # Save task info with original URL
                                                task_info = {
                                                    'task_id': task_id,
                                                    'model': 'bytedance/flux-dev',
                                                    'prompt': prompt,
                                                    'result_url': img_url,
                                                    'drive_info': drive_result,
                                                    'timestamp': time.time()
                                                }
                                                st.session_state.tasks.append(task_info)
                        else:
                            st.error("No images generated")
                    else:
                        st.error("Generation failed or timed out")
                else:
                    st.error("Failed to create task")
    
    # Tab 2: Image Edit (Qwen)
    with tab2:
        st.subheader("Image Edit with Qwen")
        
        # Prompt library selector for image edits
        selected_prompt = prompt_library_selector(default_category="Image Edits")
        if selected_prompt:
            st.session_state.selected_prompt_for_generation = selected_prompt
            st.rerun()
        
        # Image source selection
        use_library = st.checkbox("Use image from library", key="qwen_use_library")
        
        image_url = None
        if use_library:
            if st.session_state.credentials:
                images = list_drive_images()
                if images:
                    image_options = {f"{img['name']}": img for img in images}
                    selected_name = st.selectbox("Select Image", list(image_options.keys()), key="qwen_lib_select")
                    selected_img = image_options[selected_name]
                    
                    # Show original URL if available, otherwise use Drive URL
                    image_url = selected_img.get('original_url') or selected_img.get('public_image_url')
                    
                    st.image(image_url, caption=selected_name, use_container_width=True)
                else:
                    st.info("No images in library")
            else:
                st.warning("Connect Google Drive to use library images")
        else:
            image_url = st.text_input("Image URL", 
                                     value=st.session_state.get('selected_image_for_edit', ''),
                                     placeholder="https://example.com/image.jpg")
        
        default_edit_prompt = st.session_state.get('selected_prompt_for_generation', 
                                                   "Make the image more vibrant and colorful")
        prompt = st.text_area("Edit Instructions", default_edit_prompt, key="qwen_prompt")
        
        if st.button("Edit Image", type="primary", key="qwen_edit"):
            if not image_url or not prompt:
                st.warning("Please provide image URL and edit instructions")
            else:
                with st.spinner("Creating edit task..."):
                    task_id = create_task("bytedance/qwen2-vl-72b-edit", {
                        "image_urls": [image_url],
                        "prompt": prompt,
                        "max_images": 1
                    })
                
                if task_id:
                    st.info(f"Task ID: {task_id}")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    result = wait_for_task(task_id, progress_bar, status_text)
                    
                    if result:
                        result_json = json.loads(result.get('resultJson', '{}'))
                        result_urls = result_json.get('resultUrls', [])
                        
                        if result_urls:
                            st.success("✅ Edit complete!")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.image(image_url, caption="Original", use_container_width=True)
                            with col2:
                                st.image(result_urls[0], caption="Edited", use_container_width=True)
                            
                            # Upload to Drive
                            if st.session_state.credentials:
                                with st.spinner("Uploading to Google Drive..."):
                                    img_bytes = download_image(result_urls[0])
                                    if img_bytes:
                                        filename = f"edited_qwen_{task_id}.png"
                                        
                                        # Create metadata with original URL
                                        metadata = {
                                            'original_url': result_urls[0],
                                            'edit_type': 'qwen',
                                            'prompt': prompt
                                        }
                                        
                                        drive_result = upload_to_gdrive(img_bytes, filename)
                                        
                                        if drive_result:
                                            st.success(f"✅ Uploaded to Drive: {filename}")
                                            
                                            task_info = {
                                                'task_id': task_id,
                                                'model': 'bytedance/qwen2-vl-72b-edit',
                                                'prompt': prompt,
                                                'result_url': result_urls[0],
                                                'drive_info': drive_result,
                                                'timestamp': time.time()
                                            }
                                            st.session_state.tasks.append(task_info)
                        else:
                            st.error("Edit failed")
                    else:
                        st.error("Edit failed or timed out")
                else:
                    st.error("Failed to create task")
    
    # Tab 3: Image Edit (Seedream)
    with tab3:
        st.subheader("Image Edit with Seedream V4")
        
        # Prompt library selector for e-commerce
        selected_prompt = prompt_library_selector(default_category="E-commerce Mockups")
        if selected_prompt:
            st.session_state.selected_prompt_for_generation = selected_prompt
            st.rerun()
        
        # Image source selection
        use_library = st.checkbox("Use image from library", key="seedream_use_library")
        
        image_url = None
        if use_library:
            if st.session_state.credentials:
                images = list_drive_images()
                if images:
                    image_options = {f"{img['name']}": img for img in images}
                    selected_name = st.selectbox("Select Image", list(image_options.keys()), key="seedream_lib_select")
                    selected_img = image_options[selected_name]
                    
                    # Show original URL if available, otherwise use Drive URL
                    image_url = selected_img.get('original_url') or selected_img.get('public_image_url')
                    
                    st.image(image_url, caption=selected_name, use_container_width=True)
                else:
                    st.info("No images in library")
            else:
                st.warning("Connect Google Drive to use library images")
        else:
            image_url = st.text_input("Image URL", 
                                     value=st.session_state.get('selected_image_for_edit', ''),
                                     placeholder="https://example.com/image.jpg",
                                     key="seedream_url")
        
        default_seedream_prompt = st.session_state.get('selected_prompt_for_generation',
                                                       "Create a professional mockup with this design")
        prompt = st.text_area("Edit Instructions", default_seedream_prompt, key="seedream_prompt")
        image_size = st.selectbox("Image Size", ["square_hd", "portrait_16_9", "landscape_16_9"], key="seedream_size")
        image_resolution = st.selectbox("Resolution", ["1K", "2K", "4K"], key="seedream_res")
        
        if st.button("Edit Image", type="primary", key="seedream_edit"):
            if not image_url or not prompt:
                st.warning("Please provide image URL and edit instructions")
            else:
                with st.spinner("Creating edit task..."):
                    task_id = create_task("bytedance/seedream-v4-edit", {
                        "image_urls": [image_url],
                        "prompt": prompt,
                        "image_size": image_size,
                        "image_resolution": image_resolution,
                        "max_images": 1
                    })
                
                if task_id:
                    st.info(f"Task ID: {task_id}")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    result = wait_for_task(task_id, progress_bar, status_text)
                    
                    if result:
                        result_json = json.loads(result.get('resultJson', '{}'))
                        result_urls = result_json.get('resultUrls', [])
                        
                        if result_urls:
                            st.success("✅ Edit complete!")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.image(image_url, caption="Original", use_container_width=True)
                            with col2:
                                st.image(result_urls[0], caption="Edited", use_container_width=True)
                            
                            # Upload to Drive
                            if st.session_state.credentials:
                                with st.spinner("Uploading to Google Drive..."):
                                    img_bytes = download_image(result_urls[0])
                                    if img_bytes:
                                        filename = f"edited_seedream_{task_id}.png"
                                        drive_result = upload_to_gdrive(img_bytes, filename)
                                        
                                        if drive_result:
                                            st.success(f"✅ Uploaded to Drive: {filename}")
                                            
                                            task_info = {
                                                'task_id': task_id,
                                                'model': 'bytedance/seedream-v4-edit',
                                                'prompt': prompt,
                                                'result_url': result_urls[0],
                                                'drive_info': drive_result,
                                                'timestamp': time.time()
                                            }
                                            st.session_state.tasks.append(task_info)
                        else:
                            st.error("Edit failed")
                    else:
                        st.error("Edit failed or timed out")
                else:
                    st.error("Failed to create task")

# Page: Upload Images
elif page == "Upload Images":
    st.header("📤 Upload Images to Google Drive")
    
    if not st.session_state.credentials:
        st.warning("⚠️ Please connect Google Drive first from the sidebar")
    else:
        st.info("Upload your images to Google Drive. They will be automatically made public and added to your library.")
        
        uploaded_files = st.file_uploader(
            "Choose images",
            type=['png', 'jpg', 'jpeg', 'webp'],
            accept_multiple_files=True
        )
        
        if uploaded_files:
            st.subheader(f"Selected {len(uploaded_files)} file(s)")
            
            # Preview
            cols = st.columns(3)
            for idx, uploaded_file in enumerate(uploaded_files):
                with cols[idx % 3]:
                    st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)
            
            if st.button("Upload All to Google Drive", type="primary"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                success_count = 0
                for idx, uploaded_file in enumerate(uploaded_files):
                    status_text.text(f"Uploading {uploaded_file.name}...")
                    
                    img_bytes = uploaded_file.getvalue()
                    drive_result = upload_to_gdrive(img_bytes, uploaded_file.name)
                    
                    if drive_result:
                        success_count += 1
                    
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                status_text.empty()
                progress_bar.empty()
                
                if success_count == len(uploaded_files):
                    st.success(f"✅ Successfully uploaded {success_count} image(s) to Google Drive!")
                else:
                    st.warning(f"⚠️ Uploaded {success_count} out of {len(uploaded_files)} image(s)")
                
                if st.button("Go to Library"):
                    st.session_state.page = "Library"
                    st.rerun()

# Page: History
elif page == "History":
    st.header("Generation History")
    
    if not st.session_state.tasks:
        st.info("No generation history yet")
    else:
        for task_info in reversed(st.session_state.tasks):
            with st.expander(f"Task: {task_info['task_id']}", expanded=False):
                st.write(f"**Model:** {task_info['model']}")
                st.write(f"**Prompt:** {task_info['prompt']}")
                st.write(f"**Time:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(task_info['timestamp']))}")
                
                if task_info.get('result_url'):
                    st.image(task_info['result_url'], use_container_width=True)
                
                if task_info.get('drive_info'):
                    drive_info = task_info['drive_info']
                    st.write(f"**Google Drive:** [View File]({drive_info['web_view_link']})")

# Page: Library
elif page == "Library":
    st.header("📚 Image Library")
    
    if not st.session_state.credentials:
        st.warning("⚠️ Please connect Google Drive first from the sidebar")
    else:
        # Controls
        col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
        
        with col1:
            search_query = st.text_input("🔍 Search", value=st.session_state.search_query, key="lib_search")
            st.session_state.search_query = search_query
        
        with col2:
            sort_by = st.selectbox("Sort by", ["Newest First", "Oldest First", "Name A-Z", "Name Z-A"], 
                                  index=["Newest First", "Oldest First", "Name A-Z", "Name Z-A"].index(st.session_state.sort_by))
            st.session_state.sort_by = sort_by
        
        with col3:
            filter_type = st.selectbox("Filter", ["All", "PNG", "JPG", "WebP"],
                                      index=["All", "PNG", "JPG", "WebP"].index(st.session_state.filter_type))
            st.session_state.filter_type = filter_type
        
        with col4:
            view_mode = st.selectbox("View", ["Grid", "List"],
                                    index=["Grid", "List"].index(st.session_state.view_mode))
            st.session_state.view_mode = view_mode
        
        with col5:
            if st.button("🔄 Refresh"):
                st.rerun()
        
        # Load images
        with st.spinner("Loading images from Google Drive..."):
            images = list_drive_images()
        
        # Filter
        if search_query:
            images = [img for img in images if search_query.lower() in img['name'].lower()]
        
        if filter_type != "All":
            mime_map = {"PNG": "image/png", "JPG": "image/jpeg", "WebP": "image/webp"}
            images = [img for img in images if img.get('mimeType') == mime_map[filter_type]]
        
        # Sort
        if sort_by == "Newest First":
            images.sort(key=lambda x: x.get('createdTime', ''), reverse=True)
        elif sort_by == "Oldest First":
            images.sort(key=lambda x: x.get('createdTime', ''))
        elif sort_by == "Name A-Z":
            images.sort(key=lambda x: x['name'])
        elif sort_by == "Name Z-A":
            images.sort(key=lambda x: x['name'], reverse=True)
        
        if not images:
            st.info("No images found in your Google Drive")
        else:
            st.success(f"Found {len(images)} image(s)")
            
            # Display
            if view_mode == "Grid":
                cols = st.columns(3)
                for idx, img in enumerate(images):
                    with cols[idx % 3]:
                        # Try to display image from original URL first, fallback to Drive URLs
                        image_url = img.get('original_url') or img.get('public_image_url') or img.get('thumbnail_url') or img.get('direct_link')
                        
                        try:
                            st.image(image_url, use_container_width=True)
                        except:
                            st.warning(f"Could not load: {img['name']}")
                        
                        st.markdown(f"**{img['name']}**")
                        
                        # Show both original and drive links if available
                        link_col1, link_col2 = st.columns(2)
                        with link_col1:
                            if img.get('original_url'):
                                st.markdown(f"[🔗 Original Link]({img['original_url']})")
                        with link_col2:
                            st.markdown(f"[📁 Drive Link]({img.get('webViewLink')})")
                        
                        # Metadata
                        size_mb = float(img.get('size', 0)) / (1024 * 1024)
                        st.caption(f"📏 {size_mb:.2f} MB | 📅 {img.get('createdTime', 'N/A')[:10]}")
                        st.caption(f"🗂️ {img.get('mimeType', 'Unknown')}")
                        
                        # Action buttons
                        btn_col1, btn_col2, btn_col3 = st.columns(3)
                        with btn_col1:
                            if st.button("✏️ Qwen", key=f"edit_qwen_{img['id']}"):
                                st.session_state.selected_image_for_edit = image_url
                                st.session_state.page = "Generate"
                                st.rerun()
                        with btn_col2:
                            if st.button("🎨 Seedream", key=f"edit_seedream_{img['id']}"):
                                st.session_state.selected_image_for_edit = image_url
                                st.session_state.page = "Generate"
                                st.rerun()
                        with btn_col3:
                            if st.button("🗑️", key=f"del_{img['id']}"):
                                if delete_drive_file(img['id']):
                                    st.success("Deleted!")
                                    st.rerun()
                        
                        st.markdown("---")
            else:
                # List view
                for img in images:
                    col1, col2 = st.columns([1, 3])
                    
                    with col1:
                        image_url = img.get('original_url') or img.get('public_image_url') or img.get('thumbnail_url') or img.get('direct_link')
                        try:
                            st.image(image_url, use_container_width=True)
                        except:
                            st.warning("Could not load")
                    
                    with col2:
                        st.markdown(f"### {img['name']}")
                        
                        size_mb = float(img.get('size', 0)) / (1024 * 1024)
                        st.write(f"**Size:** {size_mb:.2f} MB | **Created:** {img.get('createdTime', 'N/A')[:10]} | **Type:** {img.get('mimeType', 'Unknown')}")
                        
                        link_col1, link_col2 = st.columns(2)
                        with link_col1:
                            if img.get('original_url'):
                                st.markdown(f"[🔗 Original Link]({img['original_url']})")
                        with link_col2:
                            st.markdown(f"[📁 Drive Link]({img.get('webViewLink')})")
                        
                        btn_col1, btn_col2, btn_col3 = st.columns(3)
                        with btn_col1:
                            if st.button("Edit with Qwen", key=f"list_edit_qwen_{img['id']}"):
                                st.session_state.selected_image_for_edit = image_url
                                st.session_state.page = "Generate"
                                st.rerun()
                        with btn_col2:
                            if st.button("Edit with Seedream", key=f"list_edit_seedream_{img['id']}"):
                                st.session_state.selected_image_for_edit = image_url
                                st.session_state.page = "Generate"
                                st.rerun()
                        with btn_col3:
                            if st.button("Delete", key=f"list_del_{img['id']}"):
                                if delete_drive_file(img['id']):
                                    st.success("Deleted!")
                                    st.rerun()
                    
                    st.markdown("---")

# Page: Prompt Library
elif page == "Prompt Library":
    st.header("📖 Prompt Library")
    
    st.info("Browse pre-made prompts or add your own custom prompts to each category")
    
    # Category tabs
    tabs = st.tabs(list(PROMPT_LIBRARY.keys()))
    
    for idx, category in enumerate(PROMPT_LIBRARY.keys()):
        with tabs[idx]:
            st.subheader(category)
            
            # Built-in prompts
            st.markdown("### 📚 Built-in Prompts")
            for i, prompt in enumerate(PROMPT_LIBRARY[category], 1):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"{i}. {prompt}")
                with col2:
                    if st.button("Use", key=f"use_{category}_{i}"):
                        st.session_state.selected_prompt_for_generation = prompt
                        st.success("Prompt selected! Go to Generate page.")
            
            st.markdown("---")
            
            # Custom prompts
            st.markdown("### ✏️ Your Custom Prompts")
            custom_prompts = st.session_state.custom_prompts.get(category, [])
            
            if custom_prompts:
                for i, prompt in enumerate(custom_prompts):
                    col1, col2, col3 = st.columns([4, 1, 1])
                    with col1:
                        st.markdown(f"⭐ {prompt}")
                    with col2:
                        if st.button("Use", key=f"use_custom_{category}_{i}"):
                            st.session_state.selected_prompt_for_generation = prompt
                            st.success("Prompt selected! Go to Generate page.")
                    with col3:
                        if st.button("🗑️", key=f"del_custom_{category}_{i}"):
                            st.session_state.custom_prompts[category].remove(prompt)
                            st.rerun()
            else:
                st.info("No custom prompts yet")
            
            # Add new custom prompt
            st.markdown("### ➕ Add Custom Prompt")
            new_prompt = st.text_area("Enter your custom prompt", key=f"new_prompt_{category}", height=100)
            if st.button("Add to Library", key=f"add_{category}"):
                if new_prompt.strip():
                    if category not in st.session_state.custom_prompts:
                        st.session_state.custom_prompts[category] = []
                    st.session_state.custom_prompts[category].append(new_prompt.strip())
                    st.success("Custom prompt added!")
                    st.rerun()
                else:
                    st.warning("Please enter a prompt")

st.markdown("---")
st.caption("Made with ❤️ using Streamlit and AI QuickDraw API")
