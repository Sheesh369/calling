import { useState, useEffect, useCallback } from 'react';
import {
  Phone,
  MessageCircle,
  Mail,
  Upload,
  RefreshCw,
  XCircle,
  Loader2,
  FileText,
  Activity,
  Search,
  Eye,
  X,
  Users,
  LogOut
} from 'lucide-react';
import logo from "./logo.png";
import * as XLSX from 'xlsx';
import { useAuth } from './context/AuthContext';
import { useNavigate } from 'react-router-dom';

// Helper function to fetch with authentication
const fetchWithAuth = async (url, options = {}) => {
  const token = localStorage.getItem('access_token');
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'ngrok-skip-browser-warning': 'true'
    }
  });
};

const colors = {
  primary: 'rgb(150, 133, 117)',
  primaryHover: 'rgb(100, 89, 78)',
  background: 'rgb(255, 255, 255)',
  backgroundSecondary: 'rgb(244, 235, 226)',
  text: 'rgb(0, 0, 0)',
  textSecondary: 'rgb(51, 51, 51)',
  border: 'rgb(200, 178, 156)',
  borderLight: 'rgb(244, 235, 226)',
};

// Add global styles for hover effects and animations
const globalStyles = `
  .logout-button:hover {
    background: rgb(150, 133, 117) !important;
    color: white !important;
  }
  .manage-users-button:hover {
    background: rgb(100, 89, 78) !important;
  }
  .change-password-button:hover {
    background: rgb(244, 235, 226) !important;
  }
  .transcript-card:hover {
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    border-color: rgb(150, 133, 117) !important;
  }
  .modal-close-button:hover {
    background: rgb(244, 235, 226) !important;
  }
  .password-submit-button:hover {
    background: rgb(100, 89, 78) !important;
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
`;

const HummingBirdLogo = () => (
  <img src={logo} alt="HummingBird Logo" style={{ width: "120px", height: "80px", objectFit: "contain" }} />
);

export default function HummingBirdMultiAgent() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  
  const [agentType, setAgentType] = useState('voice');
  const [backendHealthy, setBackendHealthy] = useState(false);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [parsedData, setParsedData] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [callStatus, setCallStatus] = useState([]);
  const [transcripts, setTranscripts] = useState([]);
  const [whatsappMessages, setWhatsappMessages] = useState([]);
  const [emailMessages, setEmailMessages] = useState([]);
  const [numToProcess, setNumToProcess] = useState(5);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [activeVoiceTab, setActiveVoiceTab] = useState('upload'); // upload, status, transcripts
  const [searchQuery, setSearchQuery] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState('all');
  const [cutOffDateFilter, setCutOffDateFilter] = useState('');
  const [expandedTranscript, setExpandedTranscript] = useState(null);
  
  // Super Admin states
  const [selectedUserId, setSelectedUserId] = useState(null); // null = own data, 0 = all users, number = specific user
  const [allUsers, setAllUsers] = useState([]);
  
  // Password change modal states
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ oldPassword: '', newPassword: '', confirmPassword: '' });
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');

  // Fixed delays - not exposed to user
  const MESSAGE_DELAY = 3; // 3 seconds

  // Track if component is mounted to prevent state updates after unmount
  const [isMounted, setIsMounted] = useState(true);

  useEffect(() => {
    return () => {
      setIsMounted(false);
    };
  }, []);

  useEffect(() => {
    checkBackendHealth();
    
    // Fetch users list if super admin
    if (user?.role === 'super_admin') {
      fetchUsers();
    }
  }, [user]);

  const fetchUsers = async () => {
    try {
      const response = await fetchWithAuth('/api/users');
      if (response.ok) {
        const data = await response.json();
        if (isMounted) {
          setAllUsers(data.users || []);
        }
      }
    } catch (err) {
      console.error('Error fetching users:', err);
    }
  };

  useEffect(() => {
    let interval;
    if (autoRefresh && agentType === 'voice' && activeVoiceTab === 'status') {
      interval = setInterval(() => {
        fetchCallStatus();
      }, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, agentType, activeVoiceTab]);

  // Consolidated: Fetch data when selectedUserId or activeVoiceTab changes
  useEffect(() => {
    const fetchData = async () => {
      if (activeVoiceTab === 'status') {
        await fetchCallStatus();
      } else if (activeVoiceTab === 'transcripts') {
        await fetchTranscripts();
      }
    };
    
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedUserId, activeVoiceTab]);

  const checkBackendHealth = async () => {
    try {
      const response = await fetch('/health', { 
        timeout: 5000,
        headers: { 'ngrok-skip-browser-warning': 'true' }
      });
      if (isMounted) {
        setBackendHealthy(response.ok);
      }
    } catch {
      if (isMounted) {
        setBackendHealthy(false);
      }
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploadedFile(file);

    try {
      const fileExtension = file.name.split('.').pop().toLowerCase();

      if (fileExtension === 'csv') {
        // Handle CSV files
        const reader = new FileReader();
        reader.onload = (event) => {
          try {
            const text = event.target.result;
            const lines = text.split('\n');
            const headers = lines[0].split(',').map(h => h.trim());

            const data = lines.slice(1).filter(line => line.trim()).map(line => {
              const values = line.split(',').map(v => v.trim());
              const row = {};
              headers.forEach((header, idx) => {
                row[header] = values[idx] || '';
              });
              return row;
            });

            setParsedData(data);
          } catch (err) {
            alert('Error parsing CSV file: ' + err.message);
          }
        };
        reader.readAsText(file);
      } else if (fileExtension === 'xlsx' || fileExtension === 'xls') {
        // Handle Excel files
        const reader = new FileReader();
        reader.onload = (event) => {
          try {
            const data = new Uint8Array(event.target.result);
            const workbook = XLSX.read(data, { type: 'array' });

            // Get first sheet
            const firstSheetName = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[firstSheetName];

            // Convert to JSON
            const jsonData = XLSX.utils.sheet_to_json(worksheet);

            setParsedData(jsonData);
          } catch (err) {
            alert('Error parsing Excel file: ' + err.message);
          }
        };
        reader.readAsArrayBuffer(file);
      } else {
        alert('Unsupported file format. Please upload CSV or Excel file.');
      }
    } catch (err) {
      alert('Error reading file: ' + err.message);
    }
  };

  const fetchCallStatus = useCallback(async () => {
    try {
      // Build query params for super admin
      let url = '/calls';
      if (user?.role === 'super_admin') {
        // Only add user_id param if a filter is selected (not null)
        if (selectedUserId !== null) {
          url += `?user_id=${selectedUserId}`;
        }
        // If selectedUserId is null, don't add param (shows super admin's own data)
      }
      
      const response = await fetchWithAuth(url);
      const data = await response.json();
      if (isMounted) {
        setCallStatus(data.calls || []);
      }
    } catch (err) {
      console.error('Error fetching call status:', err);
    }
  }, [user?.role, selectedUserId, isMounted]);

  const fetchTranscripts = useCallback(async () => {
    try {
      // Build query params for super admin
      let url = '/transcripts';
      if (user?.role === 'super_admin') {
        // Only add user_id param if a filter is selected (not null)
        if (selectedUserId !== null) {
          url += `?user_id=${selectedUserId}`;
        }
        // If selectedUserId is null, don't add param (shows super admin's own data)
      }
      
      const response = await fetchWithAuth(url);
      const data = await response.json();

      // Also fetch call status to match phone numbers
      let callsUrl = '/calls';
      if (user?.role === 'super_admin') {
        if (selectedUserId !== null) {
          callsUrl += `?user_id=${selectedUserId}`;
        }
      }
      
      const callsResponse = await fetchWithAuth(callsUrl);
      const callsData = await callsResponse.json();

      // Create a map of call_uuid to call data
      const callMap = {};
      callsData.calls?.forEach(call => {
        callMap[call.call_uuid] = call;
      });

      // Enrich transcripts with phone number from calls
      const enrichedTranscripts = data.transcripts?.map(transcript => {
        const call = callMap[transcript.call_uuid];
        return {
          ...transcript,
          phone_number: call?.phone_number || 'N/A'
        };
      }) || [];

      if (isMounted) {
        setTranscripts(enrichedTranscripts);
      }
    } catch (err) {
      console.error('Error fetching transcripts:', err);
    }
  }, [user?.role, selectedUserId, isMounted]);

  const initiateVoiceCalls = async () => {
    if (!parsedData || parsedData.length === 0) return;

    setIsProcessing(true);
    const processCount = Math.min(numToProcess, parsedData.length);

    try {
      // Prepare batch payload
      const calls = parsedData.slice(0, processCount).map(row => ({
        phone_number: row.phone_number,
        body: {
          customer_name: row.customer_name,
          invoice_number: row.invoice_number,
          invoice_date: row.invoice_date,
          total_amount: row.total_amount,
          outstanding_balance: row.outstanding_balance
        }
      }));

      // Send batch request to backend with authentication
      const response = await fetchWithAuth('/start_batch', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ calls })
      });

      if (response.ok) {
        const data = await response.json();
        console.log(`Batch request successful: ${data.message}`);
        
        // Switch to status tab immediately
        setActiveVoiceTab('status');
        
        // Start polling for status updates
        const pollInterval = setInterval(async () => {
          try {
            await fetchCallStatus();
            
            // Check if all calls are completed
            let statusUrl = '/calls';
            if (user?.role === 'super_admin') {
              if (selectedUserId !== null) {
                statusUrl += `?user_id=${selectedUserId}`;
              }
            }
            
            const statusResponse = await fetchWithAuth(statusUrl);
            const statusData = await statusResponse.json();
            const allCompleted = data.call_uuids.every(uuid => {
              const call = statusData.calls?.find(c => c.call_uuid === uuid);
              return call && (call.status === 'completed' || call.status === 'failed');
            });
            
            if (allCompleted) {
              clearInterval(pollInterval);
              setIsProcessing(false);
              console.log('All calls completed');
            }
          } catch (err) {
            console.error('Error polling status:', err);
          }
        }, 3000); // Poll every 3 seconds for UI updates
        
      } else {
        console.error('Batch request failed:', await response.text());
        setIsProcessing(false);
      }
    } catch (err) {
      console.error('Error initiating batch calls:', err);
      setIsProcessing(false);
    }
  };

  const sendWhatsAppMessages = async () => {
    if (!parsedData || parsedData.length === 0) return;

    setIsProcessing(true);
    const processCount = Math.min(numToProcess, parsedData.length);
    const messages = [];

    for (let i = 0; i < processCount; i++) {
      const row = parsedData[i];
      try {
        const payload = {
          phone_number: row.phone_number,
          body: {
            customer_name: row.customer_name,
            invoice_number: row.invoice_number,
            invoice_date: row.invoice_date,
            total_amount: row.total_amount,
            outstanding_balance: row.outstanding_balance
          }
        };

        const response = await fetch('/whatsapp/send', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
          },
          body: JSON.stringify(payload)
        });

        if (response.ok) {
          messages.push({
            phone_number: row.phone_number,
            customer_name: row.customer_name,
            status: 'sent',
            sent_at: new Date().toISOString()
          });
        }

        // Use fixed 3 second delay
        await new Promise(resolve => setTimeout(resolve, MESSAGE_DELAY * 1000));
      } catch (err) {
        console.error('Error sending WhatsApp:', err);
      }
    }

    setWhatsappMessages(prev => [...messages, ...prev]);
    setIsProcessing(false);
  };

  const sendEmails = async () => {
    if (!parsedData || parsedData.length === 0) return;

    setIsProcessing(true);
    const processCount = Math.min(numToProcess, parsedData.length);
    const emails = [];

    for (let i = 0; i < processCount; i++) {
      const row = parsedData[i];
      try {
        const payload = {
          email: row.email,
          body: {
            customer_name: row.customer_name,
            invoice_number: row.invoice_number,
            invoice_date: row.invoice_date,
            total_amount: row.total_amount,
            outstanding_balance: row.outstanding_balance
          }
        };

        const response = await fetch('/email/send', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
          },
          body: JSON.stringify(payload)
        });

        if (response.ok) {
          const data = await response.json();
          emails.push({
            email: row.email,
            customer_name: row.customer_name,
            subject: data.subject,
            status: 'sent',
            sent_at: new Date().toISOString()
          });
        }

        // Use fixed 3 second delay
        await new Promise(resolve => setTimeout(resolve, MESSAGE_DELAY * 1000));
      } catch (err) {
        console.error('Error sending email:', err);
      }
    }

    setEmailMessages(prev => [...emails, ...prev]);
    setIsProcessing(false);
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess('');

    // Validate passwords match
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setPasswordError('New passwords do not match');
      return;
    }

    // Validate password length
    if (passwordForm.newPassword.length < 6) {
      setPasswordError('Password must be at least 6 characters long');
      return;
    }

    try {
      const response = await fetchWithAuth('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          old_password: passwordForm.oldPassword,
          new_password: passwordForm.newPassword
        })
      });

      if (response.ok) {
        setPasswordSuccess('Password changed successfully!');
        setPasswordForm({ oldPassword: '', newPassword: '', confirmPassword: '' });
        setTimeout(() => {
          setShowPasswordModal(false);
          setPasswordSuccess('');
        }, 2000);
      } else {
        const data = await response.json();
        // Handle both string errors and validation error arrays
        if (typeof data.detail === 'string') {
          setPasswordError(data.detail);
        } else if (Array.isArray(data.detail)) {
          // Pydantic validation errors
          setPasswordError(data.detail.map(err => err.msg).join(', '));
        } else {
          setPasswordError('Failed to change password');
        }
      }
    } catch (err) {
      setPasswordError('Network error. Please try again.');
    }
  };

  // Handle logout with proper cleanup
  const handleLogout = useCallback(() => {
    setShowPasswordModal(false);
    setExpandedTranscript(null);
    
    setTimeout(() => {
      logout();
      navigate('/login');
    }, 0);
  }, [logout, navigate]);

  // Handle password modal close with batched updates
  const closePasswordModal = useCallback(() => {
    setShowPasswordModal(false);
    setTimeout(() => {
      setPasswordForm({ oldPassword: '', newPassword: '', confirmPassword: '' });
      setPasswordError('');
      setPasswordSuccess('');
    }, 0);
  }, []);

  // Handle transcript modal close
  const closeTranscriptModal = useCallback(() => {
    setExpandedTranscript(null);
  }, []);

  const renderAgentSelector = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {[
        { id: 'voice', icon: Phone, label: 'Voice Agent' },
        { id: 'whatsapp', icon: MessageCircle, label: 'WhatsApp Agent' },
        { id: 'email', icon: Mail, label: 'Email Agent' }
      ].map(agent => (
        <button
          key={agent.id}
          onClick={() => setAgentType(agent.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '1rem',
            background: agentType === agent.id ? colors.backgroundSecondary : colors.background,
            border: `1px solid ${agentType === agent.id ? colors.primary : colors.borderLight}`,
            borderRadius: '8px',
            cursor: 'pointer',
            transition: 'all 0.2s',
            fontWeight: agentType === agent.id ? '600' : '400',
            color: colors.text
          }}
        >
          <agent.icon size={20} color={colors.primary} />
          <span>{agent.label}</span>
        </button>
      ))}
    </div>
  );

  const renderFileUpload = () => (
    <div style={{
      background: colors.background,
      borderRadius: '8px',
      padding: '2rem',
      border: `1px solid ${colors.borderLight}`
    }}>
      <h3 style={{ fontSize: '1.125rem', fontWeight: '600', marginBottom: '1rem', color: colors.text }}>
        Upload Data File
      </h3>

      <div style={{
        border: `2px dashed ${colors.border}`,
        borderRadius: '8px',
        padding: '2rem',
        textAlign: 'center',
        background: '#FAFAFA'
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <Upload size={32} color={colors.primary} style={{ marginBottom: '1rem' }} />
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={handleFileUpload}
            style={{ display: 'none' }}
            id="file-upload"
          />
          <label htmlFor="file-upload" style={{
            display: 'inline-block',
            padding: '0.75rem 1.5rem',
            background: colors.primary,
            color: 'white',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '0.875rem'
          }}>
            Choose File
          </label>
        </div>
        <p style={{ marginTop: '1rem', fontSize: '0.8125rem', color: colors.textSecondary }}>
          Supported formats: CSV, Excel (.xlsx, .xls)
        </p>
        {uploadedFile && (
          <p style={{ marginTop: '1rem', color: colors.textSecondary, fontSize: '0.875rem' }}>
            Selected: {uploadedFile.name}
          </p>
        )}
      </div>

      {parsedData && (
        <div style={{ marginTop: '1.5rem' }}>
          <p style={{ color: colors.text, marginBottom: '0.75rem', fontWeight: '600' }}>
            ✅ {parsedData.length} records loaded
          </p>
          <div style={{
            maxHeight: '200px',
            overflowY: 'auto',
            border: `1px solid ${colors.borderLight}`,
            borderRadius: '6px',
            fontSize: '0.875rem'
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ background: colors.backgroundSecondary, position: 'sticky', top: 0 }}>
                <tr>
                  {Object.keys(parsedData[0] || {}).map(key => (
                    <th key={key} style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>
                      {key}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {parsedData.slice(0, 5).map((row, idx) => (
                  <tr key={idx} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                    {Object.values(row).map((val, vIdx) => (
                      <td key={vIdx} style={{ padding: '0.75rem', color: colors.textSecondary }}>
                        {val}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );

  const renderVoiceTabs = () => (
    <div style={{
      display: 'flex',
      gap: '0.5rem',
      marginBottom: '1.5rem',
      borderBottom: `2px solid ${colors.borderLight}`
    }}>
      {[
        { id: 'upload', label: 'Upload Data', icon: Upload },
        { id: 'status', label: 'Call Status', icon: Activity },
        { id: 'transcripts', label: 'Transcripts', icon: FileText }
      ].map(tab => (
        <button
          key={tab.id}
          onClick={() => setActiveVoiceTab(tab.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '1rem 1.5rem',
            background: 'transparent',
            border: 'none',
            borderBottom: `3px solid ${activeVoiceTab === tab.id ? colors.primary : 'transparent'}`,
            cursor: 'pointer',
            fontWeight: activeVoiceTab === tab.id ? '600' : '400',
            color: activeVoiceTab === tab.id ? colors.primary : colors.textSecondary,
            fontSize: '0.9375rem',
            transition: 'all 0.2s'
          }}
        >
          <tab.icon size={18} />
          {tab.label}
        </button>
      ))}
    </div>
  );

  const renderUploadTab = () => (
    <>
      {renderFileUpload()}

      {parsedData && (
        <div style={{
          background: colors.background,
          borderRadius: '8px',
          padding: '2rem',
          border: `1px solid ${colors.borderLight}`,
          marginTop: '1.5rem'
        }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: '600', marginBottom: '1.5rem', color: colors.text }}>
            Initiate Calls
          </h3>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: colors.textSecondary }}>
              Number of calls
            </label>
            <input
              type="number"
              value={numToProcess}
              onChange={(e) => setNumToProcess(parseInt(e.target.value))}
              min="1"
              max={parsedData.length}
              style={{
                width: '100%',
                padding: '0.75rem',
                border: `1px solid ${colors.borderLight}`,
                borderRadius: '6px',
                fontSize: '0.9375rem'
              }}
            />
            <p style={{ fontSize: '0.8125rem', color: colors.textSecondary, marginTop: '0.5rem' }}>
              ℹ️ Calls will be made sequentially. Each new call starts automatically after the previous call completes.
            </p>
          </div>

          <button
            onClick={initiateVoiceCalls}
            disabled={isProcessing}
            style={{
              width: '100%',
              padding: '1rem',
              background: colors.primary,
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: isProcessing ? 'not-allowed' : 'pointer',
              fontWeight: '600',
              fontSize: '0.9375rem',
              opacity: isProcessing ? 0.6 : 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem'
            }}
          >
            {isProcessing ? (
              <>
                <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                Processing...
              </>
            ) : (
              <>
                <Phone size={16} />
                Start Sequential Calling
              </>
            )}
          </button>
        </div>
      )}
    </>
  );

  const renderStatusTab = () => (
    <div style={{
      background: colors.background,
      borderRadius: '8px',
      padding: '2rem',
      border: `1px solid ${colors.borderLight}`
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h3 style={{ fontSize: '1.125rem', fontWeight: '600', color: colors.text }}>
          Call Status
        </h3>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh
          </label>
          <button
            onClick={fetchCallStatus}
            style={{
              padding: '0.5rem 1rem',
              background: colors.primary,
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.875rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      {callStatus.length > 0 ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
            <div style={{ padding: '1rem', background: colors.backgroundSecondary, borderRadius: '6px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: '600', color: colors.text }}>{callStatus.length}</div>
              <div style={{ fontSize: '0.875rem', color: colors.textSecondary }}>Total Calls</div>
            </div>
            <div style={{ padding: '1rem', background: colors.backgroundSecondary, borderRadius: '6px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: '600', color: '#4CAF50' }}>
                {callStatus.filter(c => c.status === 'completed').length}
              </div>
              <div style={{ fontSize: '0.875rem', color: colors.textSecondary }}>Completed</div>
            </div>
            <div style={{ padding: '1rem', background: colors.backgroundSecondary, borderRadius: '6px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: '600', color: '#FF9800' }}>
                {callStatus.filter(c => ['calling', 'connected', 'in_progress'].includes(c.status)).length}
              </div>
              <div style={{ fontSize: '0.875rem', color: colors.textSecondary }}>In Progress</div>
            </div>
            <div style={{ padding: '1rem', background: colors.backgroundSecondary, borderRadius: '6px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: '600', color: '#F44336' }}>
                {callStatus.filter(c => c.status === 'failed').length}
              </div>
              <div style={{ fontSize: '0.875rem', color: colors.textSecondary }}>Failed</div>
            </div>
          </div>

          <div style={{
            maxHeight: '400px',
            overflowY: 'auto',
            border: `1px solid ${colors.borderLight}`,
            borderRadius: '6px'
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead style={{ background: colors.backgroundSecondary, position: 'sticky', top: 0 }}>
                <tr>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Customer</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Invoice</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Phone</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Status</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Created</th>
                </tr>
              </thead>
              <tbody>
                {callStatus.map((call, idx) => (
                  <tr key={idx} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>{call.customer_name}</td>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>{call.invoice_number}</td>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>{call.phone_number}</td>
                    <td style={{ padding: '0.75rem' }}>
                      <span style={{
                        padding: '0.25rem 0.75rem',
                        borderRadius: '12px',
                        fontSize: '0.8125rem',
                        fontWeight: '500',
                        background: call.status === 'completed' ? '#E8F5E9' :
                          call.status === 'failed' ? '#FFEBEE' : '#FFF3E0',
                        color: call.status === 'completed' ? '#2E7D32' :
                          call.status === 'failed' ? '#C62828' : '#F57C00'
                      }}>
                        {call.status}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>
                      {new Date(call.created_at).toLocaleString('en-IN', { 
                        year: 'numeric', 
                        month: '2-digit', 
                        day: '2-digit', 
                        hour: '2-digit', 
                        minute: '2-digit', 
                        second: '2-digit',
                        hour12: false 
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p style={{ textAlign: 'center', color: colors.textSecondary, padding: '2rem' }}>
          No calls initiated yet
        </p>
      )}
    </div>
  );

  const renderTranscriptsTab = () => {
    // Filter transcripts based on search query, outcome filter, and cut-off date
    const filteredTranscripts = transcripts.filter(transcript => {
      const searchLower = searchQuery.toLowerCase();
      const matchesSearch = (
        transcript.customer_name?.toLowerCase().includes(searchLower) ||
        transcript.invoice_number?.toLowerCase().includes(searchLower) ||
        transcript.phone_number?.toLowerCase().includes(searchLower) ||
        transcript.status?.toLowerCase().includes(searchLower)
      );
      
      // Updated to handle multiple outcomes (array)
      const matchesOutcome = outcomeFilter === 'all' || 
        (transcript.call_outcomes && Array.isArray(transcript.call_outcomes) && 
         transcript.call_outcomes.includes(outcomeFilter));
      
      // Cut-off date filter (only applies when outcome is CUT_OFF_DATE_PROVIDED and date is selected)
      let matchesCutOffDate = true;
      if (outcomeFilter === 'CUT_OFF_DATE_PROVIDED' && cutOffDateFilter) {
        matchesCutOffDate = transcript.cut_off_date === cutOffDateFilter;
      }
      
      return matchesSearch && matchesOutcome && matchesCutOffDate;
    });

    const handleTranscriptClick = async (transcript) => {
      // Set expanded transcript with basic info immediately to show modal
      setExpandedTranscript({
        ...transcript,
        transcript: null, // Set to null initially to show loading state
        summary: null
      });

      try {
        // Fetch full transcript content from backend
        const response = await fetch(`/transcripts/${transcript.filename}`, {
          headers: { 'ngrok-skip-browser-warning': 'true' }
        });
        const data = await response.json();

        // Update expanded transcript with full data
        setExpandedTranscript(prev => ({
          ...prev,
          full_content: data.full_content,
          transcript: data.sections?.conversation || '',
          summary: data.sections?.summary || ''
        }));
      } catch (err) {
        console.error('Error fetching transcript details:', err);
        // Still show modal with basic info even if content fetch fails
        setExpandedTranscript(prev => ({
          ...prev,
          transcript: 'Failed to load transcript content.',
          summary: 'Failed to load summary.'
        }));
      }
    };

    return (
      <>
        <div style={{
          background: colors.background,
          borderRadius: '8px',
          padding: '2rem',
          border: `1px solid ${colors.borderLight}`
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '1.125rem', fontWeight: '600', color: colors.text }}>
              Transcripts
            </h3>
            <button
              onClick={fetchTranscripts}
              style={{
                padding: '0.5rem 1rem',
                background: colors.primary,
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.875rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}
            >
              <RefreshCw size={14} />
              Refresh
            </button>
          </div>

          {/* Search Bar */}
          <div style={{ marginBottom: '1.5rem', position: 'relative' }}>
            <div style={{ position: 'relative' }}>
              <Search size={18} style={{
                position: 'absolute',
                left: '0.75rem',
                top: '50%',
                transform: 'translateY(-50%)',
                color: colors.textSecondary
              }} />
              <input
                type="text"
                placeholder="Search by customer name, invoice number, phone, or status..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.75rem 0.75rem 0.75rem 2.5rem',
                  border: `1px solid ${colors.borderLight}`,
                  borderRadius: '6px',
                  fontSize: '0.9375rem',
                  outline: 'none',
                  transition: 'border-color 0.2s'
                }}
                onFocus={(e) => e.target.style.borderColor = colors.primary}
                onBlur={(e) => e.target.style.borderColor = colors.borderLight}
              />
            </div>
            {searchQuery && (
              <p style={{ fontSize: '0.8125rem', color: colors.textSecondary, marginTop: '0.5rem' }}>
                Found {filteredTranscripts.length} result(s)
              </p>
            )}
          </div>

          {/* Call Outcome Filter */}
          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: '600', color: colors.text }}>
              Filter by Call Outcome
            </label>
            <select
              value={outcomeFilter}
              onChange={(e) => {
                setOutcomeFilter(e.target.value);
                // Clear date filter when outcome changes away from CUT_OFF_DATE_PROVIDED
                if (e.target.value !== 'CUT_OFF_DATE_PROVIDED') {
                  setCutOffDateFilter('');
                }
              }}
              style={{
                width: '100%',
                padding: '0.75rem',
                border: `1px solid ${colors.borderLight}`,
                borderRadius: '6px',
                fontSize: '0.9375rem',
                outline: 'none',
                cursor: 'pointer',
                background: colors.background,
                color: colors.text
              }}
              onFocus={(e) => e.target.style.borderColor = colors.primary}
              onBlur={(e) => e.target.style.borderColor = colors.borderLight}
            >
              <option value="all">All Outcomes</option>
              <option value="CUT_OFF_DATE_PROVIDED">Cut-off Date Provided</option>
              <option value="LEDGER_NEEDED">Ledger Needed</option>
              <option value="INVOICE_DETAILS_NEEDED">Invoice Details Needed</option>
              <option value="HUMAN_AGENT_NEEDED">Human Agent Needed</option>
              <option value="ALREADY_PAID">Already Paid</option>
              <option value="NO_COMMITMENT">No Commitment</option>
              <option value="FAILED">Failed</option>
            </select>
          </div>

          {/* Cut-off Date Filter - Only shows when CUT_OFF_DATE_PROVIDED is selected */}
          {outcomeFilter === 'CUT_OFF_DATE_PROVIDED' && (
            <div style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: '600', color: colors.text }}>
                Filter by Cut-off Date (Optional)
              </label>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <input
                  type="date"
                  value={cutOffDateFilter}
                  onChange={(e) => setCutOffDateFilter(e.target.value)}
                  style={{
                    flex: 1,
                    padding: '0.75rem',
                    border: `1px solid ${colors.borderLight}`,
                    borderRadius: '6px',
                    fontSize: '0.9375rem',
                    outline: 'none',
                    background: colors.background,
                    color: colors.text,
                    cursor: 'pointer'
                  }}
                  onFocus={(e) => e.target.style.borderColor = colors.primary}
                  onBlur={(e) => e.target.style.borderColor = colors.borderLight}
                />
                {cutOffDateFilter && (
                  <button
                    onClick={() => setCutOffDateFilter('')}
                    style={{
                      padding: '0.75rem 1rem',
                      background: colors.backgroundSecondary,
                      color: colors.text,
                      border: `1px solid ${colors.borderLight}`,
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                      fontWeight: '500',
                      whiteSpace: 'nowrap'
                    }}
                  >
                    Clear Date
                  </button>
                )}
              </div>
            </div>
          )}

          {filteredTranscripts.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {filteredTranscripts.map((transcript, idx) => (
                <div key={idx} 
                  className="transcript-card"
                  style={{
                    padding: '1.5rem',
                    background: '#FAFAFA',
                    borderRadius: '6px',
                    border: `1px solid ${colors.borderLight}`,
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  onClick={() => handleTranscriptClick(transcript)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                    <div style={{ flex: 1 }}>
                      <h4 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '0.5rem', color: colors.text }}>
                        {transcript.customer_name} - {transcript.invoice_number}
                      </h4>
                      <p style={{ fontSize: '0.875rem', color: colors.textSecondary, marginBottom: '0.25rem' }}>
                        Phone: {transcript.phone_number}
                      </p>
                      {transcript.call_outcomes && transcript.call_outcomes.includes('CUT_OFF_DATE_PROVIDED') && transcript.cut_off_date && (
                        <p style={{ fontSize: '0.875rem', color: colors.text, marginBottom: '0.25rem', fontWeight: '500' }}>
                          Cut-off Date: {new Date(transcript.cut_off_date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                        </p>
                      )}
                      <p style={{ fontSize: '0.875rem', color: colors.textSecondary }}>
                        Status: {transcript.status} | Created: {new Date(transcript.created_at).toLocaleString('en-IN', { 
                          year: 'numeric', 
                          month: '2-digit', 
                          day: '2-digit', 
                          hour: '2-digit', 
                          minute: '2-digit', 
                          second: '2-digit',
                          hour12: false 
                        })}
                      </p>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                      {/* Display multiple outcome badges */}
                      {transcript.call_outcomes && Array.isArray(transcript.call_outcomes) && transcript.call_outcomes.length > 0 && 
                        transcript.call_outcomes.map((outcome, idx) => (
                          outcome !== 'UNKNOWN' && (
                            <span key={idx} style={{
                              padding: '0.25rem 0.75rem',
                              background: 
                                outcome === 'CUT_OFF_DATE_PROVIDED' ? '#E3F2FD' :
                                outcome === 'LEDGER_NEEDED' ? '#FFF3E0' :
                                outcome === 'INVOICE_DETAILS_NEEDED' ? '#FCE4EC' :
                                outcome === 'HUMAN_AGENT_NEEDED' ? '#FFEBEE' :
                                outcome === 'ALREADY_PAID' ? '#E8F5E9' :
                                outcome === 'NO_COMMITMENT' ? '#F3E5F5' : '#F5F5F5',
                              color:
                                outcome === 'CUT_OFF_DATE_PROVIDED' ? '#1565C0' :
                                outcome === 'LEDGER_NEEDED' ? '#E65100' :
                                outcome === 'INVOICE_DETAILS_NEEDED' ? '#C2185B' :
                                outcome === 'HUMAN_AGENT_NEEDED' ? '#C62828' :
                                outcome === 'ALREADY_PAID' ? '#2E7D32' :
                                outcome === 'NO_COMMITMENT' ? '#6A1B9A' : '#616161',
                              borderRadius: '12px',
                              fontSize: '0.8125rem',
                              fontWeight: '500'
                            }}>
                              {outcome.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())}
                            </span>
                          )
                        ))
                      }
                      {transcript.has_summary && (
                        <span style={{
                          padding: '0.25rem 0.75rem',
                          background: '#E8F5E9',
                          color: '#2E7D32',
                          borderRadius: '12px',
                          fontSize: '0.8125rem',
                          fontWeight: '500'
                        }}>
                          ✓ Summary
                        </span>
                      )}
                      <Eye size={18} color={colors.primary} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ textAlign: 'center', color: colors.textSecondary, padding: '2rem' }}>
              {searchQuery || outcomeFilter !== 'all' ? 'No transcripts match your filters' : 'No transcripts available yet'}
            </p>
          )}
        </div>

        {/* Transcript Detail Modal */}
        {expandedTranscript && (
          <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '2rem'
          }}
            onClick={closeTranscriptModal}
          >
            <div style={{
              background: colors.background,
              borderRadius: '12px',
              maxWidth: '800px',
              width: '100%',
              maxHeight: '80vh',
              overflow: 'auto',
              boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)'
            }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div style={{
                padding: '1.5rem 2rem',
                borderBottom: `1px solid ${colors.borderLight}`,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                position: 'sticky',
                top: 0,
                background: colors.background,
                zIndex: 1
              }}>
                <div>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: '600', margin: '0 0 0.5rem 0', color: colors.text }}>
                    {expandedTranscript.customer_name}
                  </h2>
                  <p style={{ fontSize: '0.875rem', color: colors.textSecondary, margin: 0 }}>
                    Invoice: {expandedTranscript.invoice_number} | Phone: {expandedTranscript.phone_number}
                  </p>
                </div>
                <button
                  onClick={closeTranscriptModal}
                  className="modal-close-button"
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    padding: '0.5rem',
                    borderRadius: '6px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                >
                  <X size={24} color={colors.text} />
                </button>
              </div>

              {/* Modal Body */}
              <div style={{ padding: '2rem' }}>
                {/* Call Information */}
                <div style={{
                  background: colors.backgroundSecondary,
                  padding: '1.5rem',
                  borderRadius: '8px',
                  marginBottom: '1.5rem'
                }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '1rem', color: colors.text }}>
                    Call Information
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', fontSize: '0.875rem' }}>
                    <div>
                      <span style={{ color: colors.textSecondary }}>Status:</span>
                      <span style={{ marginLeft: '0.5rem', fontWeight: '600', color: colors.text }}>
                        {expandedTranscript.status}
                      </span>
                    </div>
                    <div>
                      <span style={{ color: colors.textSecondary }}>Created:</span>
                      <span style={{ marginLeft: '0.5rem', fontWeight: '600', color: colors.text }}>
                        {new Date(expandedTranscript.created_at).toLocaleString('en-IN', { 
                          year: 'numeric', 
                          month: '2-digit', 
                          day: '2-digit', 
                          hour: '2-digit', 
                          minute: '2-digit', 
                          second: '2-digit',
                          hour12: false 
                        })}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Transcript Content */}
                {expandedTranscript.transcript && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <h3 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '1rem', color: colors.text }}>
                      Conversation Transcript
                    </h3>
                    <div style={{
                      background: '#FAFAFA',
                      padding: '1.5rem',
                      borderRadius: '8px',
                      border: `1px solid ${colors.borderLight}`,
                      fontSize: '0.875rem',
                      lineHeight: '1.6',
                      color: colors.text,
                      whiteSpace: 'pre-wrap',
                      maxHeight: '300px',
                      overflowY: 'auto'
                    }}>
                      {expandedTranscript.transcript}
                    </div>
                  </div>
                )}

                {/* Summary */}
                {expandedTranscript.summary && (
                  <div>
                    <h3 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '1rem', color: colors.text }}>
                      AI-Generated Summary
                    </h3>
                    <div style={{
                      background: '#E8F5E9',
                      padding: '1.5rem',
                      borderRadius: '8px',
                      fontSize: '0.875rem',
                      lineHeight: '1.6',
                      color: colors.text,
                      whiteSpace: 'pre-wrap'
                    }}>
                      {expandedTranscript.summary}
                    </div>
                  </div>
                )}

                {/* No Content Message */}
                {expandedTranscript.transcript === null && expandedTranscript.summary === null && (
                  <div style={{ textAlign: 'center', padding: '3rem' }}>
                    <Loader2 size={32} color={colors.primary} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 1rem' }} />
                    <p style={{ color: colors.textSecondary }}>
                      Loading transcript content...
                    </p>
                  </div>
                )}
                {expandedTranscript.transcript !== null && expandedTranscript.summary !== null && !expandedTranscript.transcript && !expandedTranscript.summary && (
                  <p style={{ textAlign: 'center', color: colors.textSecondary, padding: '2rem' }}>
                    No transcript content available for this call
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </>
    );
  };

  const renderVoiceAgent = () => (
    <div>
      {renderVoiceTabs()}
      {activeVoiceTab === 'upload' && renderUploadTab()}
      {activeVoiceTab === 'status' && renderStatusTab()}
      {activeVoiceTab === 'transcripts' && renderTranscriptsTab()}
    </div>
  );

  const renderWhatsAppAgent = () => (
    <div>
      {renderFileUpload()}

      {parsedData && (
        <div style={{
          background: colors.background,
          borderRadius: '8px',
          padding: '2rem',
          border: `1px solid ${colors.borderLight}`,
          marginTop: '1.5rem'
        }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: '600', marginBottom: '1.5rem', color: colors.text }}>
            Send WhatsApp Messages
          </h3>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: colors.textSecondary }}>
              Number of messages
            </label>
            <input
              type="number"
              value={numToProcess}
              onChange={(e) => setNumToProcess(parseInt(e.target.value))}
              min="1"
              max={parsedData.length}
              style={{
                width: '100%',
                padding: '0.75rem',
                border: `1px solid ${colors.borderLight}`,
                borderRadius: '6px',
                fontSize: '0.9375rem'
              }}
            />
            <p style={{ fontSize: '0.8125rem', color: colors.textSecondary, marginTop: '0.5rem' }}>
              ℹ️ Messages will be sent with 3 seconds interval between each message
            </p>
          </div>

          <button
            onClick={sendWhatsAppMessages}
            disabled={isProcessing}
            style={{
              width: '100%',
              padding: '1rem',
              background: colors.primary,
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: isProcessing ? 'not-allowed' : 'pointer',
              fontWeight: '600',
              fontSize: '0.9375rem',
              opacity: isProcessing ? 0.6 : 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem'
            }}
          >
            {isProcessing ? (
              <>
                <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                Sending...
              </>
            ) : (
              <>
                <MessageCircle size={16} />
                Send WhatsApp Messages
              </>
            )}
          </button>
        </div>
      )}

      {whatsappMessages.length > 0 && (
        <div style={{
          background: colors.background,
          borderRadius: '8px',
          padding: '2rem',
          border: `1px solid ${colors.borderLight}`,
          marginTop: '1.5rem'
        }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: '600', marginBottom: '1.5rem', color: colors.text }}>
            Sent Messages
          </h3>

          <div style={{
            maxHeight: '400px',
            overflowY: 'auto',
            border: `1px solid ${colors.borderLight}`,
            borderRadius: '6px'
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead style={{ background: colors.backgroundSecondary, position: 'sticky', top: 0 }}>
                <tr>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Customer</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Phone</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Status</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Sent At</th>
                </tr>
              </thead>
              <tbody>
                {whatsappMessages.map((msg, idx) => (
                  <tr key={idx} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>{msg.customer_name}</td>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>{msg.phone_number}</td>
                    <td style={{ padding: '0.75rem' }}>
                      <span style={{
                        padding: '0.25rem 0.75rem',
                        borderRadius: '12px',
                        fontSize: '0.8125rem',
                        fontWeight: '500',
                        background: '#E8F5E9',
                        color: '#2E7D32'
                      }}>
                        {msg.status}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>
                      {new Date(msg.sent_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );

  const renderEmailAgent = () => (
    <div>
      {renderFileUpload()}

      {parsedData && (
        <div style={{
          background: colors.background,
          borderRadius: '8px',
          padding: '2rem',
          border: `1px solid ${colors.borderLight}`,
          marginTop: '1.5rem'
        }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: '600', marginBottom: '1.5rem', color: colors.text }}>
            Send Emails
          </h3>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: colors.textSecondary }}>
              Number of emails
            </label>
            <input
              type="number"
              value={numToProcess}
              onChange={(e) => setNumToProcess(parseInt(e.target.value))}
              min="1"
              max={parsedData.length}
              style={{
                width: '100%',
                padding: '0.75rem',
                border: `1px solid ${colors.borderLight}`,
                borderRadius: '6px',
                fontSize: '0.9375rem'
              }}
            />
            <p style={{ fontSize: '0.8125rem', color: colors.textSecondary, marginTop: '0.5rem' }}>
              ℹ️ Emails will be sent with 3 seconds interval between each email
            </p>
          </div>

          <button
            onClick={sendEmails}
            disabled={isProcessing}
            style={{
              width: '100%',
              padding: '1rem',
              background: colors.primary,
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: isProcessing ? 'not-allowed' : 'pointer',
              fontWeight: '600',
              fontSize: '0.9375rem',
              opacity: isProcessing ? 0.6 : 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem'
            }}
          >
            {isProcessing ? (
              <>
                <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                Sending...
              </>
            ) : (
              <>
                <Mail size={16} />
                Send Emails
              </>
            )}
          </button>
        </div>
      )}

      {emailMessages.length > 0 && (
        <div style={{
          background: colors.background,
          borderRadius: '8px',
          padding: '2rem',
          border: `1px solid ${colors.borderLight}`,
          marginTop: '1.5rem'
        }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: '600', marginBottom: '1.5rem', color: colors.text }}>
            Sent Emails
          </h3>

          <div style={{
            maxHeight: '400px',
            overflowY: 'auto',
            border: `1px solid ${colors.borderLight}`,
            borderRadius: '6px'
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead style={{ background: colors.backgroundSecondary, position: 'sticky', top: 0 }}>
                <tr>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Customer</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Email</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Subject</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Status</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: '600' }}>Sent At</th>
                </tr>
              </thead>
              <tbody>
                {emailMessages.map((email, idx) => (
                  <tr key={idx} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>{email.customer_name}</td>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>{email.email}</td>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>{email.subject}</td>
                    <td style={{ padding: '0.75rem' }}>
                      <span style={{
                        padding: '0.25rem 0.75rem',
                        borderRadius: '12px',
                        fontSize: '0.8125rem',
                        fontWeight: '500',
                        background: '#E8F5E9',
                        color: '#2E7D32'
                      }}>
                        {email.status}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem', color: colors.textSecondary }}>
                      {new Date(email.sent_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <>
      <style>{globalStyles}</style>
      <div style={{ minHeight: '100vh', background: '#FAFAFA', fontFamily: '"Cormorant Garamond", "Playfair Display", serif' }}>
        {/* Header */}
        <header style={{
          background: colors.background,
        borderBottom: `1px solid ${colors.borderLight}`,
        padding: '1.25rem 0',
        position: 'sticky',
        top: 0,
        zIndex: 50,
        backdropFilter: 'blur(10px)',
        backgroundColor: 'rgba(255, 255, 255, 0.95)'
      }}>
        <div style={{
          maxWidth: '1600px',
          margin: '0 auto',
          padding: '0 2rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <HummingBirdLogo />
            <div>
              <h1 style={{
                fontSize: '1.5rem',
                fontWeight: '600',
                color: colors.text,
                margin: 0,
                letterSpacing: '-0.01em'
              }}>
                HUMMINGBIRD
              </h1>
              <p style={{
                fontSize: '0.75rem',
                color: colors.textSecondary,
                margin: 0,
                letterSpacing: '0.05em'
              }}>
                MULTI-AGENT SYSTEM
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
            {/* Super Admin User Selector */}
            {user?.role === 'super_admin' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Users size={18} color={colors.primary} />
                <select
                  value={
                    selectedUserId === null ? 'own' : 
                    selectedUserId === 0 ? 'all' : 
                    selectedUserId.toString()
                  }
                  onChange={(e) => {
                    const value = e.target.value;
                    if (value === 'own') {
                      setSelectedUserId(null);
                    } else if (value === 'all') {
                      setSelectedUserId(0);
                    } else {
                      setSelectedUserId(parseInt(value));
                    }
                    // Data will refresh automatically via useEffect
                  }}
                  style={{
                    padding: '0.5rem 0.75rem',
                    border: `1px solid ${colors.borderLight}`,
                    borderRadius: '6px',
                    fontSize: '0.875rem',
                    outline: 'none',
                    cursor: 'pointer',
                    background: colors.background,
                    color: colors.text,
                    minWidth: '180px'
                  }}
                >
                  <option value="own">My Data Only</option>
                  <option value="all">All Users (Consolidated)</option>
                  {allUsers.filter(u => u.id !== user.id).map(u => (
                    <option key={u.id} value={u.id.toString()}>User: {u.username}</option>
                  ))}
                </select>
              </div>
            )}

            {/* User Info & Logout */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              {/* User Management Button - Only for Super Admin */}
              {user?.role === 'super_admin' && (
                <>
                  <button
                    onClick={() => navigate('/users')}
                    className="manage-users-button"
                    style={{
                      padding: '0.5rem 1rem',
                      background: colors.primary,
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                      fontWeight: '500',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      transition: 'all 0.2s'
                    }}
                  >
                    <Users size={16} />
                    Manage Users
                  </button>
                </>
              )}
              
              {/* Change Password Button - For All Users */}
              <button
                onClick={() => setShowPasswordModal(true)}
                className="change-password-button"
                style={{
                  padding: '0.5rem 1rem',
                  background: colors.backgroundSecondary,
                  color: colors.text,
                  border: `1px solid ${colors.borderLight}`,
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: '500',
                  transition: 'all 0.2s'
                }}
              >
                Change Password
              </button>
              
              <div style={{ textAlign: 'right' }}>
                <p style={{ fontSize: '0.875rem', fontWeight: '600', color: colors.text, margin: 0 }}>
                  {user?.username}
                </p>
                <p style={{ fontSize: '0.75rem', color: colors.textSecondary, margin: 0 }}>
                  {user?.role === 'super_admin' ? 'Super Admin' : 'User'}
                </p>
              </div>
              <button
                onClick={handleLogout}
                className="logout-button"
                style={{
                  padding: '0.5rem 1rem',
                  background: colors.backgroundSecondary,
                  color: colors.text,
                  border: `1px solid ${colors.borderLight}`,
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: '500',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  transition: 'all 0.2s'
                }}
              >
                <LogOut size={16} />
                Logout
              </button>
            </div>

            {/* Backend Status */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              fontSize: '0.875rem',
              color: backendHealthy ? '#2E7D32' : '#C62828'
            }}>
              <div style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: backendHealthy ? '#4CAF50' : '#F44336'
              }}></div>
              <span style={{ fontWeight: '500' }}>{backendHealthy ? 'Connected' : 'Offline'}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Black Bar */}
      <div style={{
        background: colors.text,
        padding: '1.25rem 0',
        borderBottom: `1px solid ${colors.border}`
      }}>
        <div style={{
          maxWidth: '1600px',
          margin: '0 auto',
          padding: '0 2rem',
          textAlign: 'center'
        }}>
          <p style={{
            fontSize: '0.9375rem',
            color: colors.background,
            margin: 0,
            fontFamily: 'Inter, sans-serif',
            fontWeight: '300',
            letterSpacing: '0.05em'
          }}>
            Automated payment reminder system for corporate India
          </p>
        </div>
      </div>

      {/* Main Content */}
      <main style={{ maxWidth: '1600px', margin: '0 auto', padding: '4rem 2rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '400px 1fr', gap: '2rem' }}>

          {/* Sidebar - Fixed */}
          <div>
            <div style={{
              background: colors.background,
              borderRadius: '8px',
              padding: '2rem',
              border: `1px solid ${colors.borderLight}`,
              position: 'sticky',
              top: '120px'
            }}>
              <h3 style={{
                fontSize: '0.875rem',
                fontWeight: '600',
                color: colors.textSecondary,
                marginBottom: '1.5rem',
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}>
                Agent Selection
              </h3>

              {renderAgentSelector()}
            </div>
          </div>

          {/* Main Content Area */}
          <div>
            {!backendHealthy && (
              <div style={{
                background: '#FFF5F5',
                border: '1px solid #FFCDD2',
                borderRadius: '8px',
                padding: '1.5rem',
                marginBottom: '2rem',
                display: 'flex',
                alignItems: 'center',
                gap: '1rem'
              }}>
                <XCircle size={24} color="#C62828" />
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: '600', color: '#C62828', margin: '0 0 0.25rem 0' }}>
                    Backend Server Offline
                  </h4>
                  <p style={{ fontSize: '0.875rem', color: '#B71C1C', margin: 0 }}>
                    Please start the backend server first: <code>python server.py</code>
                  </p>
                </div>
              </div>
            )}

            {agentType === 'voice' && renderVoiceAgent()}
            {agentType === 'whatsapp' && renderWhatsAppAgent()}
            {agentType === 'email' && renderEmailAgent()}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer style={{
        borderTop: `1px solid ${colors.borderLight}`,
        padding: '2rem 0',
        marginTop: '4rem'
      }}>
        <div style={{
          maxWidth: '1600px',
          margin: '0 auto',
          padding: '0 2rem',
          textAlign: 'center',
          fontSize: '0.875rem',
          color: colors.textSecondary
        }}>
          <p style={{ margin: 0 }}>
            Hummingbird Multi-Agent Payment Reminder System | Powered by Pipecat, Plivo, WhatsApp & Email
          </p>
        </div>
      </footer>

      </div>

      {/* Change Password Modal */}
      {showPasswordModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '2rem'
        }}
          onClick={closePasswordModal}
        >
          <div style={{
            background: colors.background,
            borderRadius: '12px',
            maxWidth: '500px',
            width: '100%',
            boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)',
            padding: '2rem'
          }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: '1.25rem', fontWeight: '600', margin: '0 0 1.5rem 0', color: colors.text }}>
              Change Password
            </h2>

            <form onSubmit={handleChangePassword}>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: '500', color: colors.text }}>
                  Current Password
                </label>
                <input
                  type="password"
                  value={passwordForm.oldPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, oldPassword: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    border: `1px solid ${colors.borderLight}`,
                    borderRadius: '6px',
                    fontSize: '0.9375rem',
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                  onFocus={(e) => e.target.style.borderColor = colors.primary}
                  onBlur={(e) => e.target.style.borderColor = colors.borderLight}
                />
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: '500', color: colors.text }}>
                  New Password
                </label>
                <input
                  type="password"
                  value={passwordForm.newPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    border: `1px solid ${colors.borderLight}`,
                    borderRadius: '6px',
                    fontSize: '0.9375rem',
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                  onFocus={(e) => e.target.style.borderColor = colors.primary}
                  onBlur={(e) => e.target.style.borderColor = colors.borderLight}
                />
              </div>

              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: '500', color: colors.text }}>
                  Confirm New Password
                </label>
                <input
                  type="password"
                  value={passwordForm.confirmPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    border: `1px solid ${colors.borderLight}`,
                    borderRadius: '6px',
                    fontSize: '0.9375rem',
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                  onFocus={(e) => e.target.style.borderColor = colors.primary}
                  onBlur={(e) => e.target.style.borderColor = colors.borderLight}
                />
              </div>

              {passwordError && (
                <div style={{
                  padding: '0.75rem',
                  background: '#FFEBEE',
                  border: '1px solid #FFCDD2',
                  borderRadius: '6px',
                  marginBottom: '1rem'
                }}>
                  <p style={{ color: '#C62828', fontSize: '0.875rem', margin: 0 }}>
                    {passwordError}
                  </p>
                </div>
              )}

              {passwordSuccess && (
                <div style={{
                  padding: '0.75rem',
                  background: '#E8F5E9',
                  border: '1px solid #C8E6C9',
                  borderRadius: '6px',
                  marginBottom: '1rem'
                }}>
                  <p style={{ color: '#2E7D32', fontSize: '0.875rem', margin: 0 }}>
                    {passwordSuccess}
                  </p>
                </div>
              )}

              <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={closePasswordModal}
                  style={{
                    padding: '0.75rem 1.5rem',
                    background: colors.backgroundSecondary,
                    color: colors.text,
                    border: `1px solid ${colors.borderLight}`,
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontSize: '0.9375rem',
                    fontWeight: '500'
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="password-submit-button"
                  style={{
                    padding: '0.75rem 1.5rem',
                    background: colors.primary,
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontSize: '0.9375rem',
                    fontWeight: '600'
                  }}
                >
                  Change Password
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
