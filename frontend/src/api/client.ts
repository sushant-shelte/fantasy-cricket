import axios from 'axios';
import { getAuth } from 'firebase/auth';

const client = axios.create({ baseURL: '' });

client.interceptors.request.use(async (config) => {
  try {
    const auth = getAuth();
    const user = auth.currentUser;
    if (user) {
      const token = await user.getIdToken();
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch {
    // Dev mode - no Firebase configured
  }
  return config;
});

export default client;
