import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface Props {
  /** The document awaiting confirmation, or null when the dialog is closed. */
  filename: string | null;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function DeleteDocumentDialog({ filename, isDeleting, onCancel, onConfirm }: Props) {
  return (
    <Dialog open={!!filename} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete Case Document</DialogTitle>
          <DialogDescription>
            Are you sure you want to remove{' '}
            <strong className="text-foreground">{filename}</strong>? This will erase all document
            data permanently.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onCancel} disabled={isDeleting}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm} loading={isDeleting}>
            Confirm Deletion
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
