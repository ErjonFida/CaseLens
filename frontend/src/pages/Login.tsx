import React, { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import * as api from '../api/client';
import { setStoredToken } from '../auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Scale, ShieldAlert, ArrowRight, Sparkles } from 'lucide-react';

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [demoAvailable, setDemoAvailable] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [registrationOpen, setRegistrationOpen] = useState(false);

  // Offer the demo only where one is seeded; a local install usually has none.
  // Registration is closed on the public demo deployment.
  useEffect(() => {
    api
      .getHealth()
      .then((h) => {
        setDemoAvailable(h.demo);
        setRegistrationOpen(h.registration);
      })
      .catch(() => undefined);
  }, []);

  const handleDemo = async () => {
    setError('');
    setDemoLoading(true);
    try {
      setStoredToken(await api.startDemo());
      navigate('/');
    } catch (err: any) {
      setError(err.message || "The demo isn't available right now. Try again later.");
    } finally {
      setDemoLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'The email or password is wrong.');
      }

      const data = await res.json();
      if (data.access_token) {
        setStoredToken(data.access_token);
        navigate('/');
      } else {
        throw new Error('Sign-in failed. Try again.');
      }
    } catch (err: any) {
      setError(err.message || 'Sign-in failed. Try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-background relative overflow-hidden">

      <Card className="w-full max-w-md border-border/80 bg-card/90 backdrop-blur-xl shadow-2xl relative z-10">
        <CardHeader className="text-center space-y-3 pb-6">
          <div className="mx-auto w-14 h-14 rounded-2xl bg-primary/10 border border-primary/25 flex items-center justify-center text-primary shadow-inner">
            <Scale className="w-7 h-7" />
          </div>
          <div>
            <CardTitle className="text-2xl font-bold tracking-tight">CaseLens</CardTitle>
            <CardDescription className="text-muted-foreground mt-1">
              Sign in to ask questions about your documents.
            </CardDescription>
          </div>
        </CardHeader>

        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            {error && (
              <Alert variant="destructive" className="py-2.5">
                <ShieldAlert className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                placeholder="attorney@firm.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
              </div>
              <Input
                id="password"
                type="password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
          </CardContent>

          <CardFooter className="flex flex-col space-y-3 pt-2">
            <Button type="submit" className="w-full font-semibold h-11" loading={loading}>
              Sign in
              {!loading && <ArrowRight className="ml-1 w-4 h-4" />}
            </Button>

            {demoAvailable && (
              <Button
                type="button"
                variant="outline"
                className="w-full h-11"
                loading={demoLoading}
                onClick={handleDemo}
              >
                {!demoLoading && <Sparkles className="mr-1 w-4 h-4" />}
                Try the demo, no account needed
              </Button>
            )}

            {registrationOpen && (
              <p className="text-center text-xs text-muted-foreground mt-2">
                No account yet?{' '}
                <Link to="/register" className="text-primary hover:underline font-medium">
                  Create one
                </Link>
              </p>
            )}
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
