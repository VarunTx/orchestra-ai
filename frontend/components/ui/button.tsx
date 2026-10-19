import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
const buttonVariants = cva('button', {variants: {variant: {default: 'button-primary', outline: 'button-outline', ghost: 'button-ghost', destructive: 'button-danger'}, size: {default: '', sm: 'button-small'}}, defaultVariants: {variant: 'default', size: 'default'}});
function Button({className, variant, size, asChild = false, ...props}: React.ComponentProps<'button'> & VariantProps<typeof buttonVariants> & {asChild?: boolean}) {
  const Comp = asChild ? Slot : 'button';
  return <Comp className={cn(buttonVariants({variant, size, className}))} {...props}/>;
}
export { Button, buttonVariants };
