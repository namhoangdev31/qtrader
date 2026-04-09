import { Injectable, Logger, BadRequestException } from '@nestjs/common';
import { OrderStatus } from './constants/order-status.enum';
import { OrderState, FillRecord } from './interfaces/order-state.interface';
import { AuditService } from '../audit-compliance/audit.service';

@Injectable()
export class OmsWorkflow {
  private readonly logger = new Logger(OmsWorkflow.name);
  
  constructor(private readonly auditService: AuditService) {}
  
  // In-memory session cache (in production, use Redis)
  private readonly orderStore = new Map<string, OrderState>();

  /**
   * Control Plane: Institutional State Machine for Order Lifecycle.
   */
  async handleTransition(orderId: string, nextStatus: OrderStatus, update: Partial<OrderState>) {
    const current = this.orderStore.get(orderId);
    if (!current) {
      throw new BadRequestException(`Order ${orderId} not found in OMS repository.`);
    }

    // 1. Enforce Valid Transitions
    if (!this.isValidTransition(current.status, nextStatus)) {
      this.logger.error(`Invalid Transition: ${current.status} -> ${nextStatus} for ${orderId}`);
      return;
    }

    // 2. Perform Transition Logic
    this.logger.log(`[OMS-WF] Transition: ${current.status} -> ${nextStatus} | Trace: ${current.traceId}`);
    
    current.status = nextStatus;
    current.updatedAt = Date.now();
    Object.assign(current, update);

    // 3. Persist and Audit (Forensic lineage)
    this.orderStore.set(orderId, current);
    await this.auditService.logForensicNote(
      `Order ${orderId} transitioned to ${nextStatus}`,
      current.traceId,
      nextStatus === OrderStatus.REJECTED ? 'ALERT' : 'INFO'
    );
  }

  async handleFill(orderId: string, fill: FillRecord) {
    const current = this.orderStore.get(orderId);
    if (!current) return;

    current.fills.push(fill);
    current.filledQuantity += fill.quantity;
    current.remainingQuantity = current.totalQuantity - current.filledQuantity;
    
    const nextStatus = current.filledQuantity >= current.totalQuantity 
      ? OrderStatus.FILLED 
      : OrderStatus.PARTIALLY_FILLED;

    await this.handleTransition(orderId, nextStatus, { 
      filledQuantity: current.filledQuantity,
      remainingQuantity: current.remainingQuantity
    });
  }

  private isValidTransition(from: OrderStatus, to: OrderStatus): boolean {
    const allowed: Record<OrderStatus, OrderStatus[]> = {
      [OrderStatus.PENDING]: [OrderStatus.ROUTED, OrderStatus.REJECTED, OrderStatus.CANCELLED],
      [OrderStatus.ROUTED]: [OrderStatus.ACKNOWLEDGED, OrderStatus.REJECTED, OrderStatus.CANCELLED],
      [OrderStatus.ACKNOWLEDGED]: [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED],
      [OrderStatus.PARTIALLY_FILLED]: [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED],
      [OrderStatus.FILLED]: [],      // Terminal
      [OrderStatus.CANCELLED]: [],   // Terminal
      [OrderStatus.REJECTED]: [],    // Terminal
      [OrderStatus.EXPIRED]: [],     // Terminal
    };
    return allowed[from].includes(to);
  }
}
