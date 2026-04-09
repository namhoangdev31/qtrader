import { Injectable, Logger } from '@nestjs/common';
import { OmsWorkflow } from './oms.workflow';
import { OrderStatus } from './constants/order-status.enum';

@Injectable()
export class OmsSubscriber {
  private readonly logger = new Logger(OmsSubscriber.name);

  constructor(private readonly omsWorkflow: OmsWorkflow) {}

  /**
   * Control Plane Subscriber: Listen for events from the hybrid event bus.
   */
  async onExecutionEvent(event: any) {
    const { orderId, type, payload, traceId } = event;
    this.logger.log(`[OMS-SUB] Received ${type} for ${orderId} | Trace: ${traceId}`);

    switch (type) {
      case 'ORDER_ACK':
        await this.omsWorkflow.handleTransition(orderId, OrderStatus.ACKNOWLEDGED, {});
        break;
      
      case 'ORDER_FILL':
        await this.omsWorkflow.handleFill(orderId, {
          fillId: payload.fillId,
          price: payload.price,
          quantity: payload.quantity,
          timestampNs: payload.timestampNs,
          venue: payload.venue,
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
