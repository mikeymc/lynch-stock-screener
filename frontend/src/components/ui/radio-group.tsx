import * as React from "react"
import * as RadioGroupPrimitive from "@radix-ui/react-radio-group"
import { Circle } from "lucide-react"

import { cn } from "@/lib/utils"

const RadioGroup = React.forwardRef(({ className, ...props }, ref) => {
    return (
        <RadioGroupPrimitive.Root
            className={cn("grid gap-2", className)}
            {...props}
            ref={ref}
        />
    )
})
RadioGroup.displayName = RadioGroupPrimitive.Root.displayName

const RadioGroupItem = React.forwardRef(({ className, ...props }, ref) => {
    return (
        <RadioGroupPrimitive.Item
            ref={ref}
            className={cn(
                "inline-flex items-center justify-center rounded-full text-primary ring-offset-background focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
                className
            )}
            style={{
                width: '16px',
                height: '16px',
                minWidth: '16px',
                maxWidth: '16px',
                minHeight: '16px',
                maxHeight: '16px',
                flexShrink: 0,
                flexGrow: 0,
                border: '1px solid hsl(var(--muted-foreground))',
                boxSizing: 'border-box',
                padding: 0
            }}
            {...props}
        >
            <RadioGroupPrimitive.Indicator className="flex items-center justify-center">
                <Circle className="h-2 w-2 fill-primary text-primary" />
            </RadioGroupPrimitive.Indicator>
        </RadioGroupPrimitive.Item>
    )
})
RadioGroupItem.displayName = RadioGroupPrimitive.Item.displayName

export { RadioGroup, RadioGroupItem }
