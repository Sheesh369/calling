// API utility for authenticated requests
// Uses relative URLs - browser automatically uses current origin
export const fetchWithAuth = async (url, options = {}) => {
  const token = localStorage.getItem('access_token');
  
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      'ngrok-skip-browser-warning': 'true'
    }
  });
};
