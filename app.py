import streamlit as st
import pandas as pd
import requests
import time
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Backend server URL
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:7860")

# Page configuration
st.set_page_config(
    page_title="Hummingbird Multi-Agent System",
    page_icon="🐦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'voice_calls' not in st.session_state:
    st.session_state.voice_calls = []
if 'whatsapp_messages' not in st.session_state:
    st.session_state.whatsapp_messages = []
if 'email_messages' not in st.session_state:
    st.session_state.email_messages = []
if 'calling_in_progress' not in st.session_state:
    st.session_state.calling_in_progress = False


def check_backend_health():
    """Check if backend server is healthy"""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


# ============= Voice Agent Functions =============
def initiate_call(phone_number, customer_data):
    """Initiate a voice call via backend API"""
    try:
        payload = {
            "phone_number": phone_number,
            "body": customer_data
        }
        response = requests.post(f"{BACKEND_URL}/start", json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to initiate call: {response.text}")
            return None
    except Exception as e:
        st.error(f"Error initiating call: {e}")
        return None


def get_call_status(call_uuid):
    """Get status of a specific call"""
    try:
        response = requests.get(f"{BACKEND_URL}/calls", timeout=10)
        if response.status_code == 200:
            calls = response.json().get("calls", [])
            for call in calls:
                if call["call_uuid"] == call_uuid:
                    return call.get("status")
        return None
    except:
        return None


def wait_for_call_completion(call_uuid, max_wait_time=300):
    """Wait for a call to complete"""
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        status = get_call_status(call_uuid)
        if status in ['completed', 'failed']:
            return True
        time.sleep(3)
    return False


def get_all_calls_status():
    """Get status of all calls from backend"""
    try:
        response = requests.get(f"{BACKEND_URL}/calls", timeout=10)
        if response.status_code == 200:
            return response.json().get("calls", [])
        return []
    except:
        return []


def get_transcripts_list():
    """Get list of all transcripts"""
    try:
        response = requests.get(f"{BACKEND_URL}/transcripts", timeout=10)
        if response.status_code == 200:
            return response.json().get("transcripts", [])
        return []
    except Exception as e:
        st.error(f"Error fetching transcripts: {e}")
        return []


def get_transcript_content(filename):
    """Get content of a specific transcript"""
    try:
        response = requests.get(f"{BACKEND_URL}/transcripts/{filename}", timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Error fetching transcript content: {e}")
        return None


# ============= WhatsApp Agent Functions =============
def send_whatsapp(phone_number, customer_data):
    """Send WhatsApp message via backend API"""
    try:
        payload = {
            "phone_number": phone_number,
            "body": customer_data
        }
        response = requests.post(f"{BACKEND_URL}/whatsapp/send", json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to send WhatsApp: {response.text}")
            return None
    except Exception as e:
        st.error(f"Error sending WhatsApp: {e}")
        return None


# ============= Email Agent Functions =============
def send_email(email, customer_data):
    """Send Email via backend API"""
    try:
        payload = {
            "email": email,
            "body": customer_data
        }
        response = requests.post(f"{BACKEND_URL}/email/send", json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to send email: {response.text}")
            return None
    except Exception as e:
        st.error(f"Error sending email: {e}")
        return None


# ============= Main UI =============
st.title("🐦 Hummingbird Multi-Agent Payment Reminder System")

# Check backend health
if not check_backend_health():
    st.error("⚠️ Backend server is not running! Please start the server first.")
    st.code("python server.py", language="bash")
    st.stop()
else:
    st.success("✅ Backend server is healthy")

# Sidebar for agent selection
st.sidebar.title("🎯 Agent Selection")
agent_type = st.sidebar.radio(
    "Choose Agent Type:",
    ["📞 Voice Agent", "💬 WhatsApp Agent", "📧 Email Agent"],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Configuration")
st.sidebar.info(f"**Backend URL:** {BACKEND_URL}")

# Show environment status
with st.sidebar.expander("🔧 Environment Status"):
    st.write("**WhatsApp:**", "✅ Configured" if os.getenv("WHATSAPP_ACCESS_TOKEN") else "❌ Not configured")
    st.write("**Email:**", "✅ Configured" if os.getenv("SMTP_USERNAME") else "❌ Not configured")
    st.write("**Plivo:**", "✅ Configured" if os.getenv("PLIVO_AUTH_ID") else "❌ Not configured")

# ============= VOICE AGENT =============
if agent_type == "📞 Voice Agent":
    st.header("📞 Voice Agent - Automated Calling")
    
    tab1, tab2, tab3 = st.tabs(["📤 Initiate Calls", "📊 Call Status", "📝 Transcripts"])
    
    # Tab 1: Initiate Calls
    with tab1:
        st.subheader("Upload Excel and Initiate Voice Calls")
        
        st.markdown("""
        **Required Excel Columns:**
        - `phone_number` - Phone number with country code (e.g., +919876543210)
        - `customer_name` - Name of the customer
        - `invoice_number` - Invoice number
        - `invoice_date` - Invoice date
        - `total_amount` - Total amount (e.g., rupees 5000)
        - `outstanding_balance` - Outstanding balance amount
        """)
        
        uploaded_file = st.file_uploader("Upload Excel file", type=['xlsx', 'xls', 'csv'], key="voice_upload")
        
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                st.success(f"✅ File uploaded successfully! Found {len(df)} records.")
                st.dataframe(df.head(10))
                
                required_columns = ['phone_number', 'customer_name', 'invoice_number', 
                                  'invoice_date', 'total_amount', 'outstanding_balance']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    st.error(f"❌ Missing required columns: {', '.join(missing_columns)}")
                else:
                    st.success("✅ All required columns present")
                    
                    st.info("📌 Calls will be initiated ONE AT A TIME. Each call must complete before the next one starts.")
                    
                    num_calls = st.number_input("Number of calls to initiate", min_value=1, max_value=len(df), 
                                              value=min(5, len(df)), key="voice_num")
                    max_wait = st.number_input("Max wait time per call (seconds)", min_value=60, max_value=600, 
                                             value=300, key="voice_wait")
                    
                    if st.button("🚀 Start Sequential Calling", disabled=st.session_state.calling_in_progress):
                        st.session_state.calling_in_progress = True
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        call_details = st.empty()
                        
                        for i in range(num_calls):
                            row = df.iloc[i]
                            status_text.text(f"📞 Initiating call {i+1}/{num_calls} to {row['customer_name']}...")
                            
                            customer_data = {
                                "customer_name": str(row['customer_name']),
                                "invoice_number": str(row['invoice_number']),
                                "invoice_date": str(row['invoice_date']),
                                "total_amount": str(row['total_amount']),
                                "outstanding_balance": str(row['outstanding_balance'])
                            }
                            
                            result = initiate_call(str(row['phone_number']), customer_data)
                            
                            if result:
                                call_uuid = result.get("call_uuid")
                                st.session_state.voice_calls.append({
                                    "call_uuid": call_uuid,
                                    "phone_number": result.get("phone_number"),
                                    "customer_name": customer_data["customer_name"],
                                    "invoice_number": customer_data["invoice_number"],
                                    "status": result.get("status"),
                                    "initiated_at": datetime.now().isoformat()
                                })
                                
                                call_details.success(f"✅ Call initiated for {row['customer_name']}")
                                status_text.text(f"⏳ Waiting for call {i+1}/{num_calls} to complete...")
                                
                                completed = wait_for_call_completion(call_uuid, max_wait_time=max_wait)
                                
                                if completed:
                                    final_status = get_call_status(call_uuid)
                                    call_details.success(f"✅ Call {i+1} completed with status: {final_status}")
                                else:
                                    call_details.warning(f"⏱️ Call {i+1} exceeded max wait time. Moving to next call...")
                                
                                if i < num_calls - 1:
                                    time.sleep(2)
                            else:
                                call_details.error(f"❌ Failed to initiate call for {row['customer_name']}")
                            
                            progress_bar.progress((i + 1) / num_calls)
                        
                        status_text.text(f"✅ Completed all {num_calls} calls!")
                        st.session_state.calling_in_progress = False
                        st.balloons()
            
            except Exception as e:
                st.error(f"Error reading file: {e}")
    
    # Tab 2: Call Status
    with tab2:
        st.subheader("Real-time Call Status")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col2:
            auto_refresh = st.checkbox("Auto-refresh (3s)", value=False, key="voice_refresh")
        with col3:
            # Export button with status filter
            status_filter = st.selectbox(
                "Filter by status",
                ["all", "completed", "failed", "calling", "in_progress", "initiated"],
                key="export_status_filter"
            )
            if st.button("📥 Export CSV", key="export_call_status"):
                try:
                    response = requests.get(
                        f"{API_BASE_URL}/api/export/call_status",
                        params={"status": status_filter},
                        headers={"Authorization": f"Bearer {st.session_state.token}"}
                    )
                    if response.status_code == 200:
                        st.download_button(
                            label="⬇️ Download CSV",
                            data=response.content,
                            file_name=f"call_status_{status_filter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                        st.success("Export ready! Click Download CSV button above.")
                    else:
                        st.error(f"Export failed: {response.text}")
                except Exception as e:
                    st.error(f"Error exporting: {e}")
        
        if st.button("🔄 Refresh Status", key="voice_refresh_btn") or auto_refresh:
            all_calls = get_all_calls_status()
            
            if all_calls:
                calls_df = pd.DataFrame(all_calls)
                status_colors = {
                    'initiated': '🟡', 'calling': '🔵', 'connected': '🟢',
                    'in_progress': '🟢', 'completed': '✅', 'failed': '❌'
                }
                calls_df['Status'] = calls_df['status'].apply(lambda x: f"{status_colors.get(x, '⚪')} {x}")
                st.dataframe(calls_df[['customer_name', 'invoice_number', 'phone_number', 'Status', 'created_at']],
                           use_container_width=True, hide_index=True)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Calls", len(all_calls))
                with col2:
                    completed = len([c for c in all_calls if c['status'] == 'completed'])
                    st.metric("Completed", completed)
                with col3:
                    in_progress = len([c for c in all_calls if c['status'] in ['calling', 'connected', 'in_progress']])
                    st.metric("In Progress", in_progress)
                with col4:
                    failed = len([c for c in all_calls if c['status'] == 'failed'])
                    st.metric("Failed", failed)
            else:
                st.info("No calls initiated yet.")
        
        if auto_refresh:
            time.sleep(3)
            st.rerun()
    
    # Tab 3: Transcripts
    with tab3:
        st.subheader("Call Transcripts & Summaries")
        
        col1, col2 = st.columns([3, 1])
        with col2:
            # Export button for transcripts
            if st.button("📥 Export Transcripts CSV", key="export_transcripts"):
                try:
                    response = requests.get(
                        f"{API_BASE_URL}/api/export/transcripts",
                        headers={"Authorization": f"Bearer {st.session_state.token}"}
                    )
                    if response.status_code == 200:
                        st.download_button(
                            label="⬇️ Download CSV",
                            data=response.content,
                            file_name=f"transcripts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                        st.success("Export ready! Click Download CSV button above.")
                    else:
                        st.error(f"Export failed: {response.text}")
                except Exception as e:
                    st.error(f"Error exporting: {e}")
        
        if st.button("🔄 Refresh Transcripts", key="voice_transcripts_refresh"):
            st.rerun()
        
        with st.spinner("Loading transcripts..."):
            transcripts = get_transcripts_list()
        
        if transcripts:
            st.success(f"Found {len(transcripts)} transcript(s)")
            
            show_only_with_summary = st.checkbox("Show only transcripts with summaries", value=False, key="voice_filter")
            filtered_transcripts = transcripts if not show_only_with_summary else [t for t in transcripts if t.get('has_summary', False)]
            
            if not filtered_transcripts:
                st.warning("No transcripts match the filter criteria")
            else:
                for transcript in filtered_transcripts:
                    with st.expander(f"📄 {transcript['customer_name']} - {transcript['invoice_number']} "
                                   f"({'✅ With Summary' if transcript.get('has_summary') else '⏳ Processing'})"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Customer:** {transcript['customer_name']}")
                            st.write(f"**Invoice:** {transcript['invoice_number']}")
                        with col2:
                            st.write(f"**Status:** {transcript['status']}")
                            st.write(f"**Created:** {transcript['created_at']}")
                        
                        if st.button(f"View Full Transcript", key=f"view_{transcript['filename']}"):
                            with st.spinner("Loading transcript content..."):
                                content = get_transcript_content(transcript['filename'])
                            
                            if content:
                                if content['sections']['conversation']:
                                    st.text_area("Conversation", content['sections']['conversation'], height=300, 
                                               key=f"conv_{transcript['filename']}")
                                
                                if content['sections']['summary']:
                                    st.markdown("### 📝 AI Summary")
                                    st.info(content['sections']['summary'])
                                else:
                                    st.warning("⏳ Summary is being generated...")
                                
                                st.download_button("📥 Download Transcript", content['full_content'],
                                                 file_name=transcript['filename'], mime="text/plain",
                                                 key=f"download_{transcript['filename']}")
        else:
            st.info("📭 No transcripts available yet.")

# ============= WHATSAPP AGENT =============
elif agent_type == "💬 WhatsApp Agent":
    st.header("💬 WhatsApp Agent - Automated Messages")
    
    st.markdown("""
    **Required Excel Columns:**
    - `phone_number` - Phone number without + (e.g., 919876543210)
    - `customer_name` - Name of the customer
    - `invoice_number` - Invoice number
    - `invoice_date` - Invoice date
    - `total_amount` - Total amount
    - `outstanding_balance` - Outstanding balance amount
    """)
    
    uploaded_file = st.file_uploader("Upload Excel file", type=['xlsx', 'xls', 'csv'], key="whatsapp_upload")
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.success(f"✅ File uploaded successfully! Found {len(df)} records.")
            st.dataframe(df.head(10))
            
            required_columns = ['phone_number', 'customer_name', 'invoice_number', 
                              'invoice_date', 'total_amount', 'outstanding_balance']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"❌ Missing required columns: {', '.join(missing_columns)}")
            else:
                st.success("✅ All required columns present")
                
                num_messages = st.number_input("Number of messages to send", min_value=1, max_value=len(df), 
                                             value=min(10, len(df)), key="whatsapp_num")
                delay = st.number_input("Delay between messages (seconds)", min_value=1, max_value=60, 
                                      value=2, key="whatsapp_delay")
                
                if st.button("📤 Send WhatsApp Messages"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i in range(num_messages):
                        row = df.iloc[i]
                        status_text.text(f"Sending message {i+1}/{num_messages} to {row['customer_name']}...")
                        
                        customer_data = {
                            "customer_name": str(row['customer_name']),
                            "invoice_number": str(row['invoice_number']),
                            "invoice_date": str(row['invoice_date']),
                            "total_amount": str(row['total_amount']),
                            "outstanding_balance": str(row['outstanding_balance'])
                        }
                        
                        result = send_whatsapp(str(row['phone_number']), customer_data)
                        
                        if result:
                            st.session_state.whatsapp_messages.append({
                                "phone_number": result.get("phone_number"),
                                "customer_name": customer_data["customer_name"],
                                "status": "sent",
                                "sent_at": datetime.now().isoformat()
                            })
                            st.success(f"✅ Message sent to {row['customer_name']}")
                        else:
                            st.error(f"❌ Failed to send message to {row['customer_name']}")
                        
                        progress_bar.progress((i + 1) / num_messages)
                        
                        if i < num_messages - 1:
                            time.sleep(delay)
                    
                    status_text.text(f"✅ Completed sending {num_messages} messages!")
                    st.balloons()
        
        except Exception as e:
            st.error(f"Error reading file: {e}")
    
    # Show sent messages
    if st.session_state.whatsapp_messages:
        st.subheader("📊 Sent Messages")
        messages_df = pd.DataFrame(st.session_state.whatsapp_messages)
        st.dataframe(messages_df, use_container_width=True, hide_index=True)

# ============= EMAIL AGENT =============
elif agent_type == "📧 Email Agent":
    st.header("📧 Email Agent - Automated Emails")
    
    st.markdown("""
    **Required Excel Columns:**
    - `email` - Email address of the customer
    - `customer_name` - Name of the customer
    - `invoice_number` - Invoice number
    - `invoice_date` - Invoice date
    - `total_amount` - Total amount
    - `outstanding_balance` - Outstanding balance amount
    """)
    
    uploaded_file = st.file_uploader("Upload Excel file", type=['xlsx', 'xls', 'csv'], key="email_upload")
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.success(f"✅ File uploaded successfully! Found {len(df)} records.")
            st.dataframe(df.head(10))
            
            required_columns = ['email', 'customer_name', 'invoice_number', 
                              'invoice_date', 'total_amount', 'outstanding_balance']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"❌ Missing required columns: {', '.join(missing_columns)}")
            else:
                st.success("✅ All required columns present")
                
                num_emails = st.number_input("Number of emails to send", min_value=1, max_value=len(df), 
                                           value=min(10, len(df)), key="email_num")
                delay = st.number_input("Delay between emails (seconds)", min_value=1, max_value=60, 
                                      value=2, key="email_delay")
                
                if st.button("📤 Send Emails"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i in range(num_emails):
                        row = df.iloc[i]
                        status_text.text(f"Sending email {i+1}/{num_emails} to {row['customer_name']}...")
                        
                        customer_data = {
                            "customer_name": str(row['customer_name']),
                            "invoice_number": str(row['invoice_number']),
                            "invoice_date": str(row['invoice_date']),
                            "total_amount": str(row['total_amount']),
                            "outstanding_balance": str(row['outstanding_balance'])
                        }
                        
                        result = send_email(str(row['email']), customer_data)
                        
                        if result:
                            st.session_state.email_messages.append({
                                "email": result.get("email"),
                                "customer_name": customer_data["customer_name"],
                                "subject": result.get("subject"),
                                "status": "sent",
                                "sent_at": datetime.now().isoformat()
                            })
                            st.success(f"✅ Email sent to {row['customer_name']}")
                        else:
                            st.error(f"❌ Failed to send email to {row['customer_name']}")
                        
                        progress_bar.progress((i + 1) / num_emails)
                        
                        if i < num_emails - 1:
                            time.sleep(delay)
                    
                    status_text.text(f"✅ Completed sending {num_emails} emails!")
                    st.balloons()
        
        except Exception as e:
            st.error(f"Error reading file: {e}")
    
    # Show sent emails
    if st.session_state.email_messages:
        st.subheader("📊 Sent Emails")
        emails_df = pd.DataFrame(st.session_state.email_messages)
        st.dataframe(emails_df, use_container_width=True, hide_index=True)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>Hummingbird Multi-Agent Payment Reminder System | Powered by Pipecat, Plivo, WhatsApp & Email</p>
    </div>
    """,
    unsafe_allow_html=True
)