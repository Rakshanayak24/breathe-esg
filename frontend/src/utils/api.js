import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) config.headers.Authorization = `Token ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('user');
      localStorage.removeItem('organisation');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export const authAPI = {
  login: (username, password) =>
    api.post('/auth/login/', { username, password }),
  logout: () => api.post('/auth/logout/'),
  me: () => api.get('/auth/me/'),
};

export const batchAPI = {
  list: (params) => api.get('/batches/', { params }),
  get: (id) => api.get(`/batches/${id}/`),
  upload: (formData) =>
    api.post('/batches/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  approve: (id, data) => api.post(`/batches/${id}/approve/`, data),
  reject: (id, data) => api.post(`/batches/${id}/reject/`, data),
  rows: (id, params) => api.get(`/batches/${id}/rows/`, { params }),
};

export const emissionsAPI = {
  list: (params) => api.get('/emission-records/', { params }),
};

export const dashboardAPI = {
  stats: () => api.get('/dashboard/stats/'),
};

export default api;
