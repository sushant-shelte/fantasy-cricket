import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';

const firebaseConfig = {
  apiKey: "AIzaSyBNFGBq5adjOIJg-Hhj1PbvdFRBm3ac2_c",
  authDomain: "cricket-fantasy-7d3ac.firebaseapp.com",
  projectId: "cricket-fantasy-7d3ac",
  storageBucket: "cricket-fantasy-7d3ac.firebasestorage.app",
  messagingSenderId: "378430689779",
  appId: "1:378430689779:web:133848c19b90fb15ccc286",
  measurementId: "G-8VL49D72YM",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export default app;
