import * as React from "react";
import { cn } from "../../lib/utils";
export const Card=React.forwardRef<HTMLElement,React.HTMLAttributes<HTMLElement>>(({className,...props},ref)=><section ref={ref} className={cn("card",className)} {...props}/>);
Card.displayName="Card";
