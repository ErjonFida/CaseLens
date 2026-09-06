import { BookOpen, Copy, LogOut, MessageSquare, Scale, Search } from 'lucide-react';
import { toast } from 'sonner';

import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

export type DashboardTab = 'chat' | 'search' | 'vault';

interface Props {
  userEmail: string;
  activeTab: DashboardTab;
  onTabChange: (tab: DashboardTab) => void;
  onSignOut: () => void;
}

export default function DashboardHeader({ userEmail, activeTab, onTabChange, onSignOut }: Props) {
  return (
    <header className="h-14 border-b border-border px-6 flex items-center justify-between bg-card/40 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
          <Scale className="w-4 h-4" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-sm font-bold tracking-tight text-foreground">
              CaseLens
            </h1>
            <Badge variant="outline" className="text-[10px] py-0 px-1.5 font-normal">
              RAG Assistant
            </Badge>
          </div>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => onTabChange(v as DashboardTab)} className="w-auto">
        <TabsList className="h-8">
          <TabsTrigger value="chat" className="text-xs gap-1.5 h-7">
            <MessageSquare className="w-3.5 h-3.5" />
            AI Assistant
          </TabsTrigger>
          <TabsTrigger value="search" className="text-xs gap-1.5 h-7">
            <Search className="w-3.5 h-3.5" />
            RAG Explorer
          </TabsTrigger>
          <TabsTrigger value="vault" className="text-xs gap-1.5 h-7">
            <BookOpen className="w-3.5 h-3.5" />
            Document Vault
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 gap-2 pl-1 pr-2 text-xs font-normal">
              <Avatar className="h-6 w-6">
                <AvatarFallback className="text-[10px] bg-primary/20 text-primary font-bold">
                  {userEmail ? userEmail.slice(0, 2).toUpperCase() : 'LA'}
                </AvatarFallback>
              </Avatar>
              <span className="hidden sm:inline-block max-w-[140px] truncate text-foreground font-medium">
                {userEmail || 'Account'}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>Practitioner Profile</DropdownMenuLabel>
            <div className="px-2.5 py-1 text-xs text-muted-foreground truncate">{userEmail}</div>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => {
                navigator.clipboard.writeText(userEmail);
                toast.success('Email copied');
              }}
              className="gap-2 text-xs"
            >
              <Copy className="w-3.5 h-3.5" /> Copy Email
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={onSignOut}
              className="gap-2 text-xs text-destructive hover:text-destructive"
            >
              <LogOut className="w-3.5 h-3.5" /> Sign Out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
