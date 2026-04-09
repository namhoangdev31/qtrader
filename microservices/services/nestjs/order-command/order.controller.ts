import { Controller, Post, Body, Headers, Logger, OnModuleInit } from '@nestjs/common';
import { Client, ClientGrpc, Transport } from '@nestjs/microservices';
import { join } from 'path';
import { v4 as uuidv4 } from 'uuid';
import { Observable } from 'rxjs';

@Controller('orders')
export class OrderController implements OnModuleInit {
  private readonly logger = new Logger(OrderController.name);

  @Client({
    transport: Transport.GRPC,
    options: {
      package: 'qtrader.v2',
      protoPath: join(__dirname, '../../proto/order.proto'),
      url: 'localhost:50051',
    },
  })
  private client: ClientGrpc;

  private executionService: any;

  onModuleInit() {
    this.executionService = this.client.getService<any>('ExecutionService');
  }

  @Post()
  async createOrder(
    @Body() orderDto: any,
    @Headers('x-trace-id') traceId: string,
    @Headers('x-session-id') sessionId: string,
  ) {
    const orderId = uuidv4();
    this.logger.log(`[ORDER-COMMAND] Dispatching Order: ${orderId} via gRPC | Trace: ${traceId}`);
    
    const command = {
      orderId,
      sessionId,
      traceId,
      symbol: orderDto.symbol,
      action: orderDto.action,
      type: orderDto.type,
      quantity: orderDto.quantity,
      price: orderDto.price,
      idempotencyKey: orderDto.idempotencyKey,
      timestampNs: Date.now() * 1000000,
    };

    // Control Plane -> Compute Plane Bridge
    return this.executionService.submitOrder(command);
  }
}
