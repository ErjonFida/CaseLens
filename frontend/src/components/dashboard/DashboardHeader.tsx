import { BookOpen, Copy, FolderOpen, LogOut, MessageSquare, Scale, Search } from 'lucide-react';
import { toast } from 'sonner';

import { Avatar, AvatarFallback } from '@/components/ui/avatar';
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
  /** Opens the document list, which is a drawer below the md breakpoint. */
  onOpenDocuments: () => void;
}

export default function DashboardHeader({ userEmail, activeTab, onTabChange, onSignOut, onOpenDocuments }: Props) {
  return (
    <header className="h-14 border-b border-border px-3 sm:px-6 flex items-center justify-between gap-2 bg-card/40 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onOpenDocuments}
          aria-label="Show documents"
          className="md:hidden text-muted-foreground hover:text-foreground"
        >
          <FolderOpen className="w-4 h-4" />
        </Button>
        <div className="hidden sm:flex w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
          <Scale className="w-4 h-4" />
        </div>
        <div className="hidden sm:block">
          <div className="flex items-center gap-2">
            <h1 className="text-sm font-bold tracking-tight text-foreground">
              CaseLens
            </h1>
          </div>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => onTabChange(v as DashboardTab)} className="w-auto">
        <TabsList className="h-8">
          <TabsTrigger value="chat" className="text-xs gap-1.5 h-7">
            <MessageSquare className="w-3.5 h-3.5" />
            <span className="sr-only lg:not-sr-only">Ask</span>
          </TabsTrigger>
          <TabsTrigger value="search" className="text-xs gap-1.5 h-7">
            <Search className="w-3.5 h-3.5" />
            <span className="sr-only lg:not-sr-only">Search</span>
          </TabsTrigger>
          <TabsTrigger value="vault" className="text-xs gap-1.5 h-7">
            <BookOpen className="w-3.5 h-3.5" />
            <span className="sr-only lg:not-sr-only">Documents</span>
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" aria-label="Account menu" className="h-8 gap-2 pl-1 pr-2 text-xs font-normal">
              <Avatar className="h-6 w-6">
                <AvatarFallback className="text-[10px] bg-primary/20 text-primary font-bold">
                  {userEmail ? userEmail.slice(0, 2).toUpperCase() : 'LA'}
                </AvatarFallback>
              </Avatar>
              <span className="hidden lg:inline-block max-w-[140px] truncate text-foreground font-medium">
                {userEmail || 'Account'}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>Signed in as</DropdownMenuLabel>
            <div className="px-2.5 py-1 text-xs text-muted-foreground truncate">{userEmail}</div>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => {
                navigator.clipboard.writeText(userEmail);
                toast.success('Email copied');
              }}
              className="gap-2 text-xs"
            >
              <Copy className="w-3.5 h-3.5" /> Copy email
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={onSignOut}
              className="gap-2 text-xs text-destructive hover:text-destructive"
            >
              <LogOut className="w-3.5 h-3.5" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
