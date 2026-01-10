import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import logo from '../logo.png';

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

const HummingBirdLogo = () => (
  <img src={logo} alt="HummingBird Logo" style={{ width: "120px", height: "80px", objectFit: "contain" }} />
);

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    const result = await login(username, password);
    
    if (result.success) {
      navigate('/dashboard');
    } else {
      setError(result.error);
    }
    setLoading(false);
  };

  return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      background: colors.backgroundSecondary,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    }}>
      <div style={{ 
        width: '100%',
        maxWidth: '420px', 
        padding: '2.5rem', 
        background: colors.background,
        borderRadius: '12px',
        boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
        border: `1px solid ${colors.borderLight}`
      }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <HummingBirdLogo />
          <h2 style={{ 
            marginTop: '1.5rem', 
            color: colors.primary,
            fontSize: '1.5rem',
            fontWeight: '600',
            marginBottom: '0.5rem'
          }}>
            Welcome Back
          </h2>
          <p style={{ 
            color: colors.textSecondary,
            fontSize: '0.875rem'
          }}>
            Sign in to access your dashboard
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ 
              display: 'block',
              marginBottom: '0.5rem',
              fontSize: '0.875rem',
              fontWeight: '500',
              color: colors.text
            }}>
              Username
            </label>
            <input
              type="text"
              placeholder="Enter your username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '0.75rem',
                border: `1px solid ${colors.borderLight}`,
                borderRadius: '6px',
                fontSize: '0.9375rem',
                outline: 'none',
                transition: 'border-color 0.2s',
                boxSizing: 'border-box'
              }}
              onFocus={(e) => e.target.style.borderColor = colors.primary}
              onBlur={(e) => e.target.style.borderColor = colors.borderLight}
            />
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ 
              display: 'block',
              marginBottom: '0.5rem',
              fontSize: '0.875rem',
              fontWeight: '500',
              color: colors.text
            }}>
              Password
            </label>
            <input
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '0.75rem',
                border: `1px solid ${colors.borderLight}`,
                borderRadius: '6px',
                fontSize: '0.9375rem',
                outline: 'none',
                transition: 'border-color 0.2s',
                boxSizing: 'border-box'
              }}
              onFocus={(e) => e.target.style.borderColor = colors.primary}
              onBlur={(e) => e.target.style.borderColor = colors.borderLight}
            />
          </div>

          {error && (
            <div style={{ 
              padding: '0.75rem',
              background: '#FFEBEE',
              border: '1px solid #FFCDD2',
              borderRadius: '6px',
              marginBottom: '1.25rem'
            }}>
              <p style={{ 
                color: '#C62828', 
                fontSize: '0.875rem',
                margin: 0
              }}>
                {error}
              </p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="login-submit-button"
            style={{
              width: '100%',
              padding: '0.875rem',
              background: loading ? colors.border : colors.primary,
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontWeight: '600',
              fontSize: '0.9375rem',
              transition: 'background 0.2s',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem'
            }}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
          <style>{`
            .login-submit-button:not(:disabled):hover {
              background: ${colors.primaryHover} !important;
            }
          `}</style>
        </form>

        <div style={{ 
          marginTop: '1.5rem',
          textAlign: 'center',
          fontSize: '0.8125rem',
          color: colors.textSecondary
        }}>
          <p style={{ margin: 0 }}>
            Default credentials: admin / admin123
          </p>
        </div>
      </div>
    </div>
  );
}
