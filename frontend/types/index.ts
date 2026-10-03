export interface TrainCard {
  train_number: string;
  train_name: string;
  source_code: string | null;
  source_name: string | null;
  destination_code: string | null;
  destination_name: string | null;
  status: string;
  current_delay_minutes: number;
  location: string | null;
  distance_km: number | null;
  duration_minutes: number | null;
  data_mode: string;
  live_enabled: boolean;
  simulated: boolean;
  last_updated: string | null;
  total_halts?: number | null;
  category?: string | null;
  next_refresh_at?: string | null;
  message?: string;
}

export interface PredictionFactor {
  name: string;
  value: string | null;
  impact_minutes: number | null;
  direction: string | null;
  explanation: string | null;
  simulated: boolean;
}

export interface PredictionBlock {
  predicted_additional_delay_minutes: number | null;
  recovery_minutes: number | null;
  final_predicted_delay_minutes: number | null;
  predicted_eta: string | null;
  eta_lower_bound: string | null;
  eta_upper_bound: string | null;
  confidence: number | null;
  confidence_label: string;
  prediction_method: string | null;
  scheduled_arrival: string | null;
}

export interface CurrentStateBlock {
  location: string | null;
  current_delay_minutes: number;
  current_speed_kmph: number | null;
  status: string | null;
  distance_covered_km: number | null;
  distance_remaining_km: number | null;
  data_source: string;
}

export interface TrajectoryPoint {
  station_code: string;
  station_name: string;
  sequence: number;
  kind: "observed" | "current" | "predicted";
  scheduled_arrival: string | null;
  predicted_arrival: string | null;
  delay_minutes: number | null;
  confidence: number | null;
  eta_lower: string | null;
  eta_upper: string | null;
  recovery_minutes: number;
}

export interface RecoverySection {
  from_station_code: string;
  from_station_name: string;
  to_station_code: string;
  to_station_name: string;
  distance_km: number;
  scheduled_running_minutes: number;
  slack_minutes: number;
  dwell_recovery_minutes: number;
  recovery_potential_minutes: number;
  classification: "HIGH" | "MEDIUM" | "LOW";
  reason: string;
}

export interface PredictionPayload {
  train_number: string;
  train_name: string;
  current_state: CurrentStateBlock;
  prediction: PredictionBlock;
  factors: PredictionFactor[];
  explanation: string;
  primary_reason: string;
  recovery_map: RecoverySection[];
  recovery_summary: {
    applied_recovery_minutes: number;
    raw_recoverable_minutes: number;
    capped_by: string | null;
  };
  trajectory: TrajectoryPoint[];
  data_mode: string;
  forecast_available: boolean;
  simulated: boolean;
  live_enabled?: boolean;
  last_state_update?: string | null;
  updated_at: string;
  next_refresh_at?: string | null;
  messages?: string[];
  message?: string;
}

export interface WeatherPayload {
  location: string | null;
  temperature: number | null;
  rainfall: number | null;
  precipitation_probability: number | null;
  wind_speed: number | null;
  visibility: number | null;
  weather_condition: string | null;
  weather_risk_score: number;
  weather_risk_label: string;
  risk_reason: string;
  is_simulated: boolean;
  source: string;
  observed_at?: string | null;
}

export interface EventItem {
  timestamp: string;
  type: string;
  message: string;
  simulated: boolean;
}
