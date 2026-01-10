const BACKEND_URL = "http://3.110.2.165:7860";

export const fetchWithAuth = async (url, options = {}) => {
  const token = localStorage.getItem('access_token');
  
  return fetch(`${BACKEND_URL}${url}`, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      'ngrok-skip-browser-warning': 'true'
    }
  });
};

export { BACKEND_URL };
