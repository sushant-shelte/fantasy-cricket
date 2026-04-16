import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import type { User as FirebaseUser } from 'firebase/auth';
import {
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
} from 'firebase/auth';
import { auth } from './firebase';
import client from '../api/client';
import type { User } from '../types';

interface AuthContextType {
  firebaseUser: FirebaseUser | null;
  profile: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  devLogin: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [profile, setProfile] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Fetch profile from backend
  const fetchProfile = async (devLogin = false, firebaseUserOverride: FirebaseUser | null = null) => {
    try {
      if (devLogin) {
        const res = await client.get('/api/auth/me', { headers: { 'X-Dev-Login': '1' } });
        setProfile(res.data);
        return;
      }

      if (firebaseUserOverride) {
        const token = await firebaseUserOverride.getIdToken();
        const res = await client.get('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
        });
        setProfile(res.data);
        return;
      }

      const res = await client.get('/api/auth/me');
      setProfile(res.data);
    } catch {
      setProfile(null);
    }
  };

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, async (user) => {
      setFirebaseUser(user);
      if (user) {
        await fetchProfile(false, user);
      } else {
        setProfile(null);
      }
      setLoading(false);
    });
    return unsub;
  }, []);

  const login = async (email: string, password: string) => {
    const cred = await signInWithEmailAndPassword(auth, email, password);
    await fetchProfile(false, cred.user);
  };

  const register = async (email: string, password: string, name: string) => {
    const cred = await createUserWithEmailAndPassword(auth, email, password);
    // Register in backend
    const token = await cred.user.getIdToken();
    await client.post(
      '/api/auth/register',
      { name },
      { headers: { Authorization: `Bearer ${token}` } }
    );
    await fetchProfile(false, cred.user);
  };

  const logout = async () => {
    await signOut(auth);
    setProfile(null);
  };

  // Dev mode login - works without Firebase
  const devLogin = async () => {
    await fetchProfile(true);
    setLoading(false);
  };

  return (
    <AuthContext.Provider
      value={{ firebaseUser, profile, loading, login, register, logout, devLogin, refreshProfile: fetchProfile }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
