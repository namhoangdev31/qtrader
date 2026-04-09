import { Controller, Get, Query, Logger } from '@nestjs/common';

@Controller('reports')
export class ReportingController {
  private readonly logger = new Logger(ReportingController.name);

  /**
   * Control Plane: Read-model API for Dashboards and Tearsheets.
   * Serves pre-calculated metrics from session-reports and trade logs.
   */
  @Get('session-summary')
  async getSessionSummary(@Query('sessionId') sessionId: string) {
    this.logger.log(`[REPORTING] Fetching summary for session: ${sessionId}`);
    
    // Logic:
    // 1. Query read-optimized storage (Clickhouse/DuckDB)
    // 2. Return metrics: Sharpe, Win-rate, Exposure overview
    return {
      sessionId,
      metrics: { sharpe: 2.1, winRate: 0.65, trades: 142 }
    };
  }
}
