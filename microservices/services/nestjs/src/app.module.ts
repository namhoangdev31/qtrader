import { MiddlewareConsumer, Module, NestModule } from '@nestjs/common';

import { RolesGuard } from '../api-gateway/guards/roles.guard';
import { AuditService } from '../audit-compliance/audit.service';
import { TraceMiddleware } from '../common/middleware/trace.middleware';
import { ConfigGovernanceService } from '../config-governance/config.service';
import { EventBusAdapter } from '../event-bus-adapter/event.adapter';
import { NotificationService } from '../notification-alert/notification.service';
import { OmsController } from '../oms-workflow/oms.controller';
import { OmsSubscriber } from '../oms-workflow/oms.subscriber';
import { OmsWorkflow } from '../oms-workflow/oms.workflow';
import { OrderController } from '../order-command/order.controller';
import { ReportingController } from '../reporting-query/reporting.controller';
import { RiskPolicyService } from '../risk-policy/risk.policy';
import { SessionController } from '../session-control/session.controller';
import { SessionService } from '../session-control/session.service';
import { HealthController } from './health.controller';

@Module({
  controllers: [
    HealthController,
    SessionController,
    OrderController,
    OmsController,
    ReportingController,
  ],
  providers: [
    RolesGuard,
    SessionService,
    RiskPolicyService,
    OmsWorkflow,
    OmsSubscriber,
    AuditService,
    NotificationService,
    EventBusAdapter,
    ConfigGovernanceService,
  ],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer): void {
    consumer.apply(TraceMiddleware).forRoutes('*');
  }
}
