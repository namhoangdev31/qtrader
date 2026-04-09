import { Injectable, Logger } from '@nestjs/common';

import { OrderStatus } from './constants/order-status.enum';
import { OmsWorkflow } from './oms.workflow';

interface ExecutionEvent {
  orderId: string;
  type: 'ORDER_ACK' | 'ORDER_FILL' | 'ORDER_REJECT';
  traceId: string;
  payload: {
    fillId?: string;
    price?: number;
    quantity?: number;
    timestampNs?: number;
    venue?: string;
  };
}

@Injectable()
export class OmsSubscriber {
  private readonly logger = new Logger(OmsSubscriber.name);

  constructor(private readonly omsWorkflow: OmsWorkflow) {}

  async onExecutionEvent(event: ExecutionEvent): Promise<void> {
    const { orderId, type, payload, traceId } = event;
    this.logger.log(`[OMS-SUB] Received ${type} for ${orderId} | Trace: ${traceId}`);

    switch (type) {
      case 'ORDER_ACK':
        await this.omsWorkflow.handleTransition(orderId, OrderStatus.ACKNOWLEDGED, {});
        break;
      case 'ORDER_FILL':
        await this.omsWorkflow.handleFill(orderId, {
          fillId: payload.fillId ?? 'fill_unknown',
          price: payload.price ?? 0,
          quantity: payload.quantity ?? 0,
          timestampNs: payload.timestampNs ?? Date.now() * 1_000_000,
          venue: payload.venue ?? 'unknown',
        });
        break;
      case 'ORDER_REJECT':
        await this.omsWorkflow.handleTransition(orderId, OrderStatus.REJECTED, {
          updatedAt: Date.now(),
        });
        break;
      default:
        this.logger.warn(`Unknown execution event type: ${type}`);
    }
  }
}
