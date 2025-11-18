import streamlit as st
import requests
import json
import time
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="AI Image Editor",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# API Configuration
BASE_URL = "https://api.kie.ai/api/v1/jobs"

# Initialize session state
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'task_history' not in st.session_state:
    st.session_state.task_history = []
if 'current_task' not in st.session_state:
    st.session_state.current_task = None

# Sidebar
with st.sidebar:
    st.image("https://via.placeholder.com/300x100/4A90E2/FFFFFF?text=AI+Image+Editor", use_container_width=True)
    st.markdown("---")
    
    st.header("⚙️ API Configuration")
    api_key = st.text_input(
        "API Key", 
        type="password", 
        value=st.session_state.api_key,
        help="Get your API key from https://kie.ai/api-key"
    )
    if api_key:
        st.session_state.api_key = api_key
    
    if st.session_state.api_key:
        st.success("✅ API Key configured")
    else:
        st.warning("⚠️ Please enter your API key")
    
    st.markdown("---")
    
    # Navigation
    st.header("📍 Navigation")
    page = st.radio(
        "Select Page",
        ["🏠 Home", "🎨 SeedReeam V4 Edit", "✨ Qwen Image Edit", "📊 Task History", "📖 Documentation"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    st.markdown("### 🔗 Quick Links")
    st.markdown("- [Get API Key](https://kie.ai/api-key)")
    st.markdown("- [API Documentation](https://kie.ai/docs)")
    st.markdown("- [Support](https://kie.ai/support)")

# Helper Functions
def create_task(api_key, model, input_params, callback_url=None):
    """Create a generation task"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": input_params
    }
    
    if callback_url:
        payload["callBackUrl"] = callback_url
    
    try:
        response = requests.post(
            f"{BASE_URL}/createTask",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                return {"success": True, "task_id": data["data"]["taskId"]}
            else:
                return {"success": False, "error": data.get('msg', 'Unknown error')}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_task_status(api_key, task_id):
    """Check task status"""
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    
    try:
        response = requests.get(
            f"{BASE_URL}/recordInfo",
            headers=headers,
            params={"taskId": task_id}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                return {"success": True, "data": data["data"]}
            else:
                return {"success": False, "error": data.get('msg', 'Unknown error')}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Page: Home
if page == "🏠 Home":
    st.title("🎨 AI Image Editor")
    st.markdown("### Transform your images with powerful AI models")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 15px; color: white;'>
            <h2>🎨 SeedReeam V4 Edit</h2>
            <p>Advanced image editing with brand showcase capabilities</p>
            <ul>
                <li>Multi-image input (up to 10 images)</li>
                <li>Multiple aspect ratios</li>
                <li>Up to 4K resolution</li>
                <li>Batch generation (1-6 images)</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 30px; border-radius: 15px; color: white;'>
            <h2>✨ Qwen Image Edit</h2>
            <p>Fast and precise image editing with fine control</p>
            <ul>
                <li>Single image editing</li>
                <li>Acceleration options</li>
                <li>Fine-tuned parameters</li>
                <li>Safety checker</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.subheader("🚀 Getting Started")
    st.markdown("""
    1. **Get your API Key**: Visit [kie.ai/api-key](https://kie.ai/api-key) to obtain your API key
    2. **Enter API Key**: Add your API key in the sidebar
    3. **Choose a Model**: Select SeedReeam V4 Edit or Qwen Image Edit from the navigation
    4. **Configure Settings**: Choose presets or customize parameters
    5. **Generate**: Click generate and wait for your results
    """)
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Tasks", len(st.session_state.task_history))
    with col2:
        successful = sum(1 for t in st.session_state.task_history if t.get('status') == 'success')
        st.metric("Successful", successful)
    with col3:
        failed = sum(1 for t in st.session_state.task_history if t.get('status') == 'fail')
        st.metric("Failed", failed)

# Page: SeedReeam V4 Edit
elif page == "🎨 SeedReeam V4 Edit":
    st.title("🎨 SeedReeam V4 Edit")
    st.markdown("Generate and edit images with multiple inputs and high resolution output")
    
    # Presets
    presets = {
        "Custom": {},
        "Brand Showcase": {
            "prompt": "Refer to this logo and create a single visual showcase for an outdoor sports brand named 'KIE AI'. Display five branded items together in one image: a packaging bag, a hat, a carton box, a wristband, and a lanyard. Use blue as the main visual color, with a fun, simple, and modern style.",
            "image_size": "square_hd",
            "image_resolution": "1K",
            "max_images": 1
        },
        "Product Photography": {
            "prompt": "Create a professional product photography setup with studio lighting, clean white background, and the product as the focal point. High-end commercial style with dramatic shadows.",
            "image_size": "landscape_4_3",
            "image_resolution": "2K",
            "max_images": 2
        },
        "Fashion Design": {
            "prompt": "Transform this into a modern fashion design concept with elegant textures, runway-ready styling, and contemporary aesthetics. Magazine quality with dramatic lighting.",
            "image_size": "portrait_4_3",
            "image_resolution": "2K",
            "max_images": 3
        },
        "Interior Design": {
            "prompt": "Redesign this space as a modern minimalist interior with natural lighting, warm tones, Scandinavian design elements, and cozy atmosphere.",
            "image_size": "landscape_16_9",
            "image_resolution": "2K",
            "max_images": 2
        },
        "Food Styling": {
            "prompt": "Style this as gourmet food photography with artistic plating, dramatic lighting, magazine-quality presentation, and elegant composition.",
            "image_size": "square_hd",
            "image_resolution": "4K",
            "max_images": 1
        },
        "Tech Product": {
            "prompt": "Create a sleek tech product showcase with modern minimalist aesthetic, blue and silver tones, professional lighting, and futuristic design elements.",
            "image_size": "landscape_16_9",
            "image_resolution": "2K",
            "max_images": 2
        }
    }
    
    preset = st.selectbox("📋 Choose a preset", list(presets.keys()))
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📝 Input Parameters")
        
        # Load preset values
        preset_data = presets.get(preset, {})
        
        prompt = st.text_area(
            "Prompt*",
            value=preset_data.get("prompt", ""),
            height=150,
            max_chars=5000,
            help="Describe how you want to edit the image (max 5000 characters)"
        )
        
        st.markdown("##### Input Images")
        num_images = st.number_input("Number of input images", min_value=1, max_value=10, value=1)
        
        image_urls = []
        for i in range(num_images):
            url = st.text_input(
                f"Image URL {i+1}*",
                key=f"seedream_img_{i}",
                value="https://file.aiquickdraw.com/custom-page/akr/section-images/1757930552966e7f2on7s.png" if i == 0 else "",
                help="URL of the image to edit (max 10MB, jpeg/png/webp)"
            )
            if url:
                image_urls.append(url)
                with st.expander(f"Preview Image {i+1}"):
                    st.image(url, use_container_width=True)
        
        with st.expander("🎛️ Advanced Settings", expanded=True):
            col_a, col_b = st.columns(2)
            
            with col_a:
                image_size = st.selectbox(
                    "Image Size",
                    options=["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"],
                    index=1 if not preset_data else ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"].index(preset_data.get("image_size", "square_hd")),
                    help="Aspect ratio of the output image"
                )
                
                image_resolution = st.selectbox(
                    "Image Resolution",
                    options=["1K", "2K", "4K"],
                    index=0 if not preset_data else ["1K", "2K", "4K"].index(preset_data.get("image_resolution", "1K")),
                    help="Pixel scale of the output image"
                )
            
            with col_b:
                max_images = st.number_input(
                    "Max Images",
                    min_value=1,
                    max_value=6,
                    value=preset_data.get("max_images", 1),
                    help="Number of images to generate (1-6)"
                )
                
                use_seed = st.checkbox("Use Custom Seed", value=False)
                seed = None
                if use_seed:
                    seed = st.number_input("Seed", min_value=0, value=42, help="Random seed for reproducibility")
            
            callback_url = st.text_input(
                "Callback URL (optional)",
                placeholder="https://your-domain.com/api/callback",
                help="URL to receive task completion notifications"
            )
        
        generate_btn = st.button("🚀 Generate Images", type="primary", use_container_width=True)
    
    with col2:
        st.subheader("📊 Results")
        
        if generate_btn:
            if not st.session_state.api_key:
                st.error("⚠️ Please enter your API key in the sidebar")
            elif not prompt:
                st.error("⚠️ Please enter a prompt")
            elif not image_urls:
                st.error("⚠️ Please provide at least one image URL")
            else:
                with st.spinner("Creating generation task..."):
                    input_params = {
                        "prompt": prompt,
                        "image_urls": image_urls,
                        "image_size": image_size,
                        "image_resolution": image_resolution,
                        "max_images": max_images
                    }
                    
                    if seed is not None:
                        input_params["seed"] = seed
                    
                    result = create_task(st.session_state.api_key, "bytedance/seedream-v4-edit", input_params, callback_url)
                    
                    if result["success"]:
                        task_id = result["task_id"]
                        st.session_state.current_task = {
                            "task_id": task_id,
                            "model": "bytedance/seedream-v4-edit",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "waiting"
                        }
                        st.session_state.task_history.append(st.session_state.current_task)
                        st.success(f"✅ Task created successfully!")
                        st.code(task_id, language=None)
                    else:
                        st.error(f"❌ Error: {result['error']}")
        
        if st.session_state.current_task:
            st.markdown("---")
            task_id = st.session_state.current_task["task_id"]
            
            col_check, col_clear = st.columns(2)
            with col_check:
                check_btn = st.button("🔄 Check Status", use_container_width=True)
            with col_clear:
                if st.button("🗑️ Clear", use_container_width=True):
                    st.session_state.current_task = None
                    st.rerun()
            
            if check_btn:
                with st.spinner("Checking status..."):
                    result = check_task_status(st.session_state.api_key, task_id)
                    
                    if result["success"]:
                        task_data = result["data"]
                        state = task_data["state"]
                        
                        st.session_state.current_task["status"] = state
                        
                        if state == "waiting":
                            st.warning("⏳ Task is waiting...")
                        elif state == "success":
                            st.success("✅ Task completed successfully!")
                            
                            result_json = json.loads(task_data["resultJson"])
                            
                            col_m1, col_m2 = st.columns(2)
                            with col_m1:
                                st.metric("Cost Time", f"{task_data.get('costTime', 0) / 1000:.2f}s")
                            with col_m2:
                                st.metric("Images", len(result_json.get("resultUrls", [])))
                            
                            st.markdown("##### 🖼️ Generated Images")
                            for idx, url in enumerate(result_json.get("resultUrls", [])):
                                st.image(url, caption=f"Generated Image {idx + 1}", use_container_width=True)
                                st.markdown(f"[📥 Download]({url})")
                        
                        elif state == "fail":
                            st.error(f"❌ Task failed: {task_data.get('failMsg', 'Unknown error')}")
                    else:
                        st.error(f"❌ Error: {result['error']}")

# Page: Qwen Image Edit
elif page == "✨ Qwen Image Edit":
    st.title("✨ Qwen Image Edit")
    st.markdown("Fast and precise image editing with fine-tuned control")
    
    # Presets
    presets = {
        "Custom": {},
        "Professional Portrait": {
            "prompt": "Professional portrait photography with studio lighting and bokeh background",
            "image_size": "portrait_4_3",
            "num_inference_steps": 30,
            "guidance_scale": 7.0,
            "acceleration": "regular"
        },
        "Product Enhancement": {
            "prompt": "Enhance product with professional lighting, clean background, commercial quality",
            "image_size": "square_hd",
            "num_inference_steps": 35,
            "guidance_scale": 5.0,
            "acceleration": "regular"
        },
        "Artistic Style": {
            "prompt": "Transform into artistic painting style with vibrant colors and expressive brushstrokes",
            "image_size": "landscape_16_9",
            "num_inference_steps": 40,
            "guidance_scale": 8.0,
            "acceleration": "none"
        },
        "Nature Enhancement": {
            "prompt": "Enhance natural scenery with vivid colors, dramatic sky, and enhanced details",
            "image_size": "landscape_16_9",
            "num_inference_steps": 30,
            "guidance_scale": 6.0,
            "acceleration": "regular"
        },
        "Quick Edit": {
            "prompt": "Quick quality enhancement",
            "image_size": "square",
            "num_inference_steps": 20,
            "guidance_scale": 4.0,
            "acceleration": "high"
        }
    }
    
    preset = st.selectbox("📋 Choose a preset", list(presets.keys()))
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📝 Input Parameters")
        
        preset_data = presets.get(preset, {})
        
        prompt = st.text_area(
            "Prompt*",
            value=preset_data.get("prompt", ""),
            height=100,
            max_chars=2000,
            help="Describe how you want to edit the image (max 2000 characters)"
        )
        
        image_url = st.text_input(
            "Image URL*",
            value="https://file.aiquickdraw.com/custom-page/akr/section-images/1755603225969i6j87xnw.jpg",
            help="URL of the image to edit (max 10MB)"
        )
        
        if image_url:
            with st.expander("Preview Input Image"):
                st.image(image_url, use_container_width=True)
        
        negative_prompt = st.text_input(
            "Negative Prompt",
            value="blurry, ugly",
            max_chars=500,
            help="What to avoid in the generation"
        )
        
        with st.expander("🎛️ Generation Settings", expanded=True):
            col_a, col_b = st.columns(2)
            
            with col_a:
                image_size = st.selectbox(
                    "Image Size",
                    options=["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"],
                    index=2 if not preset_data else ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"].index(preset_data.get("image_size", "landscape_4_3")),
                )
                
                num_images = st.selectbox(
                    "Number of Images",
                    options=[1, 2, 3, 4],
                    help="How many variations to generate"
                )
                
                acceleration = st.selectbox(
                    "Acceleration",
                    options=["none", "regular", "high"],
                    index=0 if not preset_data else ["none", "regular", "high"].index(preset_data.get("acceleration", "none")),
                    help="Higher acceleration = faster generation"
                )
            
            with col_b:
                num_inference_steps = st.slider(
                    "Inference Steps",
                    min_value=2,
                    max_value=49,
                    value=preset_data.get("num_inference_steps", 25),
                    help="More steps = higher quality but slower"
                )
                
                guidance_scale = st.slider(
                    "Guidance Scale",
                    min_value=0.0,
                    max_value=20.0,
                    value=preset_data.get("guidance_scale", 4.0),
                    step=0.1,
                    help="How closely to follow the prompt"
                )
                
                output_format = st.selectbox(
                    "Output Format",
                    options=["png", "jpeg"]
                )
        
        with st.expander("⚙️ Advanced Options"):
            use_seed = st.checkbox("Use Custom Seed", value=False)
            seed = None
            if use_seed:
                seed = st.number_input("Seed", min_value=0, value=42)
            
            enable_safety = st.checkbox("Enable Safety Checker", value=True)
            sync_mode = st.checkbox("Sync Mode", value=False, help="Wait for completion in single request")
            
            callback_url = st.text_input("Callback URL (optional)", placeholder="https://your-domain.com/api/callback")
        
        generate_btn = st.button("🚀 Generate Images", type="primary", use_container_width=True)
    
    with col2:
        st.subheader("📊 Results")
        
        if generate_btn:
            if not st.session_state.api_key:
                st.error("⚠️ Please enter your API key in the sidebar")
            elif not prompt:
                st.error("⚠️ Please enter a prompt")
            elif not image_url:
                st.error("⚠️ Please provide an image URL")
            else:
                with st.spinner("Creating generation task..."):
                    input_params = {
                        "prompt": prompt,
                        "image_url": image_url,
                        "acceleration": acceleration,
                        "image_size": image_size,
                        "num_inference_steps": num_inference_steps,
                        "guidance_scale": guidance_scale,
                        "sync_mode": sync_mode,
                        "num_images": str(num_images),
                        "enable_safety_checker": enable_safety,
                        "output_format": output_format,
                        "negative_prompt": negative_prompt
                    }
                    
                    if seed is not None:
                        input_params["seed"] = seed
                    
                    result = create_task(st.session_state.api_key, "qwen/image-edit", input_params, callback_url)
                    
                    if result["success"]:
                        task_id = result["task_id"]
                        st.session_state.current_task = {
                            "task_id": task_id,
                            "model": "qwen/image-edit",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "waiting"
                        }
                        st.session_state.task_history.append(st.session_state.current_task)
                        st.success(f"✅ Task created successfully!")
                        st.code(task_id, language=None)
                    else:
                        st.error(f"❌ Error: {result['error']}")
        
        if st.session_state.current_task:
            st.markdown("---")
            task_id = st.session_state.current_task["task_id"]
            
            col_check, col_clear = st.columns(2)
            with col_check:
                check_btn = st.button("🔄 Check Status", use_container_width=True)
            with col_clear:
                if st.button("🗑️ Clear", use_container_width=True):
                    st.session_state.current_task = None
                    st.rerun()
            
            if check_btn:
                with st.spinner("Checking status..."):
                    result = check_task_status(st.session_state.api_key, task_id)
                    
                    if result["success"]:
                        task_data = result["data"]
                        state = task_data["state"]
                        
                        st.session_state.current_task["status"] = state
                        
                        if state == "waiting":
                            st.warning("⏳ Task is waiting...")
                        elif state == "success":
                            st.success("✅ Task completed successfully!")
                            
                            result_json = json.loads(task_data["resultJson"])
                            
                            col_m1, col_m2 = st.columns(2)
                            with col_m1:
                                st.metric("Cost Time", f"{task_data.get('costTime', 0) / 1000:.2f}s")
                            with col_m2:
                                st.metric("Images", len(result_json.get("resultUrls", [])))
                            
                            st.markdown("##### 🖼️ Generated Images")
                            for idx, url in enumerate(result_json.get("resultUrls", [])):
                                st.image(url, caption=f"Generated Image {idx + 1}", use_container_width=True)
                                st.markdown(f"[📥 Download]({url})")
                        
                        elif state == "fail":
                            st.error(f"❌ Task failed: {task_data.get('failMsg', 'Unknown error')}")
                    else:
                        st.error(f"❌ Error: {result['error']}")

# Page: Task History
elif page == "📊 Task History":
    st.title("📊 Task History")
    
    if not st.session_state.task_history:
        st.info("No tasks yet. Start generating images to see your history here!")
    else:
        # Filter options
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            filter_model = st.selectbox("Filter by Model", ["All", "bytedance/seedream-v4-edit", "qwen/image-edit"])
        with col2:
            filter_status = st.selectbox("Filter by Status", ["All", "waiting", "success", "fail"])
        with col3:
            if st.button("🗑️ Clear History", use_container_width=True):
                st.session_state.task_history = []
                st.rerun()
        
        st.markdown("---")
        
        # Filter tasks
        filtered_tasks = st.session_state.task_history
        if filter_model != "All":
            filtered_tasks = [t for t in filtered_tasks if t.get("model") == filter_model]
        if filter_status != "All":
            filtered_tasks = [t for t in filtered_tasks if t.get("status") == filter_status]
        
        # Display tasks
        for i, task in enumerate(reversed(filtered_tasks)):
            with st.expander(f"Task {len(filtered_tasks) - i}: {task['model']} - {task['status'].upper()}", expanded=(i == 0)):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"**Task ID:** `{task['task_id']}`")
                    st.markdown(f"**Model:** {task['model']}")
                    st.markdown(f"**Timestamp:** {task['timestamp']}")
                with col2:
                    status_color = {"waiting": "🟡", "success": "🟢", "fail": "🔴"}
                    st.markdown(f"### {status_color.get(task['status'], '⚪')} {task['status'].upper()}")
                
                if st.button(f"🔄 Check Status", key=f"check_{i}"):
                    result = check_task_status(st.session_state.api_key, task['task_id'])
                    if result["success"]:
                        st.json(result["data"])
                    else:
                        st.error(result["error"])

# Page: Documentation
elif page == "📖 Documentation":
    st.title("📖 Documentation")
    
    tab1, tab2, tab3 = st.tabs(["🎨 SeedReeam V4", "✨ Qwen Image Edit", "🔧 API Usage"])
    
    with tab1:
        st.markdown("""
        ## SeedReeam V4 Edit
        
        ### Overview
        Advanced image editing model with support for multiple input images and high-resolution output.
        
        ### Key Features
        - **Multi-Image Input**: Up to 10 input images
        - **High Resolution**: Up to 4K output
        - **Batch Generation**: Generate 1-6 images per request
        - **Flexible Aspect Ratios**: 6 different size options
        
        ### Parameters
        
        | Parameter | Type | Description |
        |-----------|------|-------------|
        | `prompt` | string | Text description (max 5000 chars) |
        | `image_urls` | array | List of image URLs (max 10) |
        | `image_size` | string | Aspect ratio (square, portrait, landscape) |
        | `image_resolution` | string | Output resolution (1K, 2K, 4K) |
        | `max_images` | number | Number of images to generate (1-6) |
        | `seed` | number | Random seed for reproducibility |
        
        ### Image Size Options
        - `square`: 1:1 Square
        - `square_hd`: 1:1 Square HD
        - `portrait_4_3`: 3:4 Portrait
        - `portrait_16_9`: 9:16 Portrait
        - `landscape_4_3`: 4:3 Landscape
        - `landscape_16_9`: 16:9 Landscape
        
        ### Best Practices
        1. Use detailed prompts for better results
        2. Start with 1K resolution for testing
        3. Use higher resolutions for final output
        4. Batch generation works best with similar prompts
        """)
    
    with tab2:
        st.markdown("""
        ## Qwen Image Edit
        
        ### Overview
        Fast and precise image editing with fine-tuned control parameters.
        
        ### Key Features
        - **Single Image Editing**: Focused on one image at a time
        - **Acceleration Options**: Speed up generation
        - **Fine Control**: Adjust inference steps and guidance
        - **Safety Checker**: Built-in content moderation
        
        ### Parameters
        
        | Parameter | Type | Range | Description |
        |-----------|------|-------|-------------|
        | `prompt` | string | - | Text description (max 2000 chars) |
        | `image_url` | string | - | Single image URL |
        | `acceleration` | string | - | none, regular, high |
        | `image_size` | string | - | Aspect ratio options |
        | `num_inference_steps` | number | 2-49 | Quality vs speed |
        | `guidance_scale` | number | 0-20 | Prompt adherence |
        | `num_images` | string | 1-4 | Number of variations |
        | `seed` | number | - | Reproducibility |
        | `negative_prompt` | string | - | What to avoid (max 500 chars) |
        | `enable_safety_checker` | boolean | - | Content moderation |
        | `output_format` | string | - | png or jpeg |
        | `sync_mode` | boolean | - | Wait for completion |
        
        ### Acceleration Levels
        - **none**: Best quality, slower
        - **regular**: Balanced speed and quality
        - **high**: Fastest, good quality
        
        ### Guidance Scale Tips
        - **Low (0-5)**: More creative freedom
        - **Medium (5-10)**: Balanced adherence
        - **High (10-20)**: Strict prompt following
        
        ### Best Practices
        1. Use negative prompts to avoid unwanted elements
        2. Adjust guidance scale based on desired control
        3. Higher inference steps = better quality
        4. Use acceleration for quick iterations
        """)
    
    with tab3:
        st.markdown("""
        ## API Usage Guide
        
        ### Authentication
        All API requests require a Bearer token:
        ```
        Authorization: Bearer YOUR_API_KEY
        ```
        
        Get your API key at: [https://kie.ai/api-key](https://kie.ai/api-key)
        
        ### Workflow
        
        #### 1. Create Task
        ```python
        POST https://api.kie.ai/api/v1/jobs/createTask
        
        {
          "model": "bytedance/seedream-v4-edit",
          "input": {
            "prompt": "Your prompt here",
            "image_urls": ["https://example.com/image.jpg"]
          }
        }
        ```
        
        #### 2. Get Task ID
        Response:
        ```json
        {
          "code": 200,
          "msg": "success",
          "data": {
            "taskId": "abc123..."
          }
        }
        ```
        
        #### 3. Check Status
        ```python
        GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=abc123...
        ```
        
        #### 4. Get Results
        When `state` is `"success"`, extract URLs from `resultJson`:
        ```json
        {
          "resultUrls": [
            "https://example.com/result1.jpg",
            "https://example.com/result2.jpg"
          ]
        }
        ```
        
        ### Callback URL (Optional)
        Receive automatic notifications when tasks complete:
        ```python
        {
          "model": "qwen/image-edit",
          "input": {...},
          "callBackUrl": "https://your-domain.com/api/callback"
        }
        ```
        
        The system will POST the complete task result to your callback URL.
        
        ### Error Codes
        
        | Code | Description |
        |------|-------------|
        | 200 | Success |
        | 400 | Invalid parameters |
        | 401 | Authentication failed |
        | 402 | Insufficient balance |
        | 404 | Resource not found |
        | 422 | Validation failed |
        | 429 | Rate limit exceeded |
        | 500 | Server error |
        
        ### Rate Limits
        - Check your account tier for specific limits
        - Use callback URLs to avoid polling
        - Batch requests when possible
        
        ### Best Practices
        1. **Always validate input parameters** before sending
        2. **Handle errors gracefully** with proper error messages
        3. **Use callbacks** for long-running tasks
        4. **Cache results** to avoid redundant requests
        5. **Monitor costs** by tracking task completion times
        6. **Test with small batches** before scaling up
        
        ### Example Code
        
        #### Python
        ```python
        import requests
        
        headers = {
            "Authorization": "Bearer YOUR_API_KEY",
            "Content-Type": "application/json"
        }
        
        # Create task
        response = requests.post(
            "https://api.kie.ai/api/v1/jobs/createTask",
            headers=headers,
            json={
                "model": "qwen/image-edit",
                "input": {
                    "prompt": "Professional portrait",
                    "image_url": "https://example.com/image.jpg"
                }
            }
        )
        
        task_id = response.json()["data"]["taskId"]
        
        # Check status
        result = requests.get(
            "https://api.kie.ai/api/v1/jobs/recordInfo",
            headers=headers,
            params={"taskId": task_id}
        )
        ```
        
        #### JavaScript
        ```javascript
        const headers = {
            "Authorization": "Bearer YOUR_API_KEY",
            "Content-Type": "application/json"
        };
        
        // Create task
        const response = await fetch(
            "https://api.kie.ai/api/v1/jobs/createTask",
            {
                method: "POST",
                headers: headers,
                body: JSON.stringify({
                    model: "bytedance/seedream-v4-edit",
                    input: {
                        prompt: "Brand showcase",
                        image_urls: ["https://example.com/image.jpg"]
                    }
                })
            }
        );
        
        const data = await response.json();
        const taskId = data.data.taskId;
        
        // Check status
        const result = await fetch(
            `https://api.kie.ai/api/v1/jobs/recordInfo?taskId=${taskId}`,
            { headers: headers }
        );
        ```
        """)
    
    st.markdown("---")
    st.info("💡 **Tip**: Use the interactive forms on the SeedReeam V4 Edit and Qwen Image Edit pages to experiment with parameters before implementing in your code!")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p><strong>AI Image Editor</strong> - Powered by KIE.AI</p>
    <p>
        <a href='https://kie.ai/api-key' target='_blank'>Get API Key</a> | 
        <a href='https://kie.ai/docs' target='_blank'>Documentation</a> | 
        <a href='https://kie.ai/support' target='_blank'>Support</a>
    </p>
    <p style='font-size: 12px; margin-top: 10px;'>
        SeedReeam V4 Edit by Bytedance | Qwen Image Edit
    </p>
</div>
""", unsafe_allow_html=True)
