import { BadRequestException, Injectable, Logger } from '@nestjs/common';

import { AuditService } from '../audit-compliance/audit.service';
import { OrderStatus } from './constants/order-status.enum';
import { FillRecord, OrderState } from './interfaces/order-state.interface';

@Injectable()
export class OmsWorkflow {
  private readonly logger = new Logger(OmsWorkflow.name);

  constructor(private readonly auditService: AuditService) {}

  private readonly orderStore = new Map<string, OrderState>();

  createOrder(input: {
    orderId: string;
    sessionId: string;
    traceId: string;
    symbol: string;
    side: 'BUY' | 'SELL';
    quantity: number;
    idempotencyKey?: string;
  }): OrderState {
    if (this.orderStore.has(input.orderId)) {
      return this.orderStore.get(input.orderId) as OrderState;
    }

    const now = Date.now();
    const created: OrderState = {
      orderId: input.orderId,
      sessionId: input.sessionId,
      traceId: input.traceId,
      symbol: input.symbol,
      status: OrderStatus.PENDING,
      side: input.side,
      totalQuantity: input.quantity,
      filledQuantity: 0,
      remainingQuantity: input.quantity,
      averagePrice: 0,
      fills: [],
      createdAt: now,
      updatedAt: now,
      idempotencyKey: input.idempotencyKey,
    };

    this.orderStore.set(input.orderId, created);
    return created;
  }

  getOrder(orderId: string): OrderState | null {
    return this.orderStore.get(orderId) ?? null;
  }

  listOrders(): OrderState[] {
    return Array.from(this.orderStore.values());
  }

  async handleTransition(
    orderId: string,
    nextStatus: OrderStatus,
    update: Partial<OrderState>,
  ): Promise<void> {
    const current = this.orderStore.get(orderId);
    if (!current) {
      throw new BadRequestException(`Order ${orderId} not found in OMS repository.`);
    }

    if (!this.isValidTransition(current.status, nextStatus)) {
      this.logger.error(`Invalid Transition: ${current.status} -> ${nextStatus} for ${orderId}`);
      return;
    }

    this.logger.log(`[OMS-WF] Transition: ${current.status} -> ${nextStatus} | Trace: ${current.traceId}`);

    current.status = nextStatus;
    current.updatedAt = Date.now();
    Object.assign(current, update);

    this.orderStore.set(orderId, current);
    await this.auditService.logForensicNote(
      `Order ${orderId} transitioned to ${nextStatus}`,
      current.traceId,
      nextStatus === OrderStatus.REJECTED ? 'ALERT' : 'INFO',
    );
  }

  async handleFill(orderId: string, fill: FillRecord): Promise<void> {
    const current = this.orderStore.get(orderId);
    if (!current) {
      return;
    }

    current.fills.push(fill);
    current.filledQuantity += fill.quantity;
    current.remainingQuantity = current.totalQuantity - current.filledQuantity;

    const nextStatus =
      current.filledQuantity >= current.totalQuantity ? OrderStatus.FILLED : OrderStatus.PARTIALLY_FILLED;

    await this.handleTransition(orderId, nextStatus, {
      filledQuantity: current.filledQuantity,
      remainingQuantity: current.remainingQuantity,
    });
  }

  private isValidTransition(from: OrderStatus, to: OrderStatus): boolean {
    const allowed: Record<OrderStatus, OrderStatus[]> = {
      [OrderStatus.PENDING]: [OrderStatus.ROUTED, OrderStatus.REJECTED, OrderStatus.CANCELLED],
      [OrderStatus.ROUTED]: [OrderStatus.ACKNOWLEDGED, OrderStatus.REJECTED, OrderStatus.CANCELLED],
      [OrderStatus.ACKNOWLEDGED]: [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED],
      [OrderStatus.PARTIALLY_FILLED]: [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED],
      [OrderStatus.FILLED]: [],
      [OrderStatus.CANCELLED]: [],
      [OrderStatus.REJECTED]: [],
      [OrderStatus.EXPIRED]: [],
    };
    return allowed[from].includes(to);
  }
}
