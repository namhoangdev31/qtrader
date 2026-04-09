import { Injectable, OnModuleDestroy } from '@nestjs/common';
import Redis from 'ioredis';

import { DEFAULT_IDEMPOTENCY_TTL_SEC } from '@common/constants';

import { OrderStatus } from './constants/order-status.enum';
import { FillRecord, OrderState } from './interfaces/order-state.interface';
import { isValidTransition } from './transition';

@Injectable()
export class OmsService implements OnModuleDestroy {
  private readonly redis: Redis;
  private readonly idempotencyTtlSec: number;

  constructor() {
    this.redis = new Redis(process.env.REDIS_URL ?? 'redis://redis:6379');
    this.idempotencyTtlSec = Number(process.env.OMS_IDEMPOTENCY_TTL_SEC ?? DEFAULT_IDEMPOTENCY_TTL_SEC);
  }

  async onModuleDestroy(): Promise<void> {
    await this.redis.quit();
  }

  private orderKey(orderId: string): string {
    return `oms:order:${orderId}`;
  }

  private idempotencyKey(key: string): string {
    return `oms:idempotency:${key}`;
  }

  async createOrder(input: {
    orderId: string;
    sessionId: string;
    traceId: string;
    symbol: string;
    side: 'BUY' | 'SELL';
    quantity: number;
    idempotencyKey?: string;
  }): Promise<OrderState> {
    if (input.idempotencyKey) {
      const existingOrderId = await this.redis.get(this.idempotencyKey(input.idempotencyKey));
      if (existingOrderId) {
        const existing = await this.getOrder(existingOrderId);
        if (existing) {
          return existing;
        }
      }
    }

    const now = Date.now();
    const state: OrderState = {
      orderId: input.orderId,
      sessionId: input.sessionId,
      traceId: input.traceId,
      symbol: input.symbol,
      status: OrderStatus.ROUTED,
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

    await this.persistOrder(state);

    if (input.idempotencyKey) {
      await this.redis.set(
        this.idempotencyKey(input.idempotencyKey),
        input.orderId,
        'EX',
        this.idempotencyTtlSec,
      );
    }

    return state;
  }

  async transitionOrder(orderId: string, nextStatus: OrderStatus): Promise<OrderState> {
    const current = await this.getOrder(orderId);
    if (!current) {
      throw new Error(`ORDER_NOT_FOUND:${orderId}`);
    }

    if (!isValidTransition(current.status, nextStatus)) {
      throw new Error(`INVALID_TRANSITION:${current.status}->${nextStatus}`);
    }

    current.status = nextStatus;
    current.updatedAt = Date.now();
    await this.persistOrder(current);
    return current;
  }

  async handleFill(orderId: string, fill: FillRecord): Promise<OrderState> {
    const current = await this.getOrder(orderId);
    if (!current) {
      throw new Error(`ORDER_NOT_FOUND:${orderId}`);
    }

    current.fills.push(fill);
    current.filledQuantity += fill.quantity;
    current.remainingQuantity = Math.max(0, current.totalQuantity - current.filledQuantity);

    if (current.filledQuantity >= current.totalQuantity) {
      current.status = OrderStatus.FILLED;
    } else {
      current.status = OrderStatus.PARTIALLY_FILLED;
    }

    current.updatedAt = Date.now();
    await this.persistOrder(current);
    return current;
  }

  async getOrder(orderId: string): Promise<OrderState | null> {
    const raw = await this.redis.get(this.orderKey(orderId));
    return raw ? (JSON.parse(raw) as OrderState) : null;
  }

  async listOrders(): Promise<OrderState[]> {
    const keys = await this.redis.keys('oms:order:*');
    if (keys.length === 0) {
      return [];
    }

    const rows = await this.redis.mget(keys);
    return rows.filter((v): v is string => Boolean(v)).map((v) => JSON.parse(v) as OrderState);
  }

  private async persistOrder(order: OrderState): Promise<void> {
    await this.redis.set(this.orderKey(order.orderId), JSON.stringify(order));
  }
}
