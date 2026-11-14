% =========================================================================
% PROPELLER DYNA PRO - MATLAB PROPULSION & AERODYNAMIC ANALYZER
% Replaces eCalc: Fits Thrust vs PWM, Thrust vs RPM^2, g/W, Ct/Cp, Kv/Kt
% =========================================================================
clear; clc; close all;

% --- 1. ENTER YOUR PROP & AMBIENT CONSTANTS ---
D_inch = 10.0;              % Propeller diameter (inches) -> Update for your prop
rho    = 1.225;             % Air density (kg/m^3) - 1.225 standard sea level
D      = D_inch * 0.0254;   % Diameter in meters

% --- 2. AUTO-LOAD LATEST STEP TEST CSV FROM logs/ ---
files = dir(fullfile('logs', 'step_test_*.csv'));
if isempty(files)
    error('No step_test_*.csv files found in logs/ folder! Run a Step Test first.');
end
[~, idx] = max([files.datenum]);
latest_csv = fullfile(files(idx).folder, files(idx).name);
fprintf('Analyzing file: %s\n\n', latest_csv);

data = readtable(latest_csv);

PWM     = data.PWM_us;
Thrust_g = data.Thrust_g;
Thrust_N = (Thrust_g / 1000) * 9.80665; % Convert grams to Newtons
RPM     = data.RPM;
Volt    = data.Voltage_V;
Curr    = data.Current_A;
Power_W = data.Power_W;
g_per_W = data.g_per_W;

% Filter active spin points (RPM > 500)
valid = RPM > 500;
n_rev_s = RPM(valid) / 60;              % Revolutions per second (Hz)
omega   = n_rev_s * 2 * pi;             % Rad/s

% --- 3. AERODYNAMIC COEFFICIENTS (Ct, Cp) & MOTOR CONSTANTS (Kv, Kt) ---
% Ct = T / (rho * n^2 * D^4)
Ct_vals = Thrust_N(valid) ./ (rho .* (n_rev_s.^2) .* (D^4));
% Cp = P_elec / (rho * n^3 * D^5)  (System electrical Cp)
Cp_vals = Power_W(valid)  ./ (rho .* (n_rev_s.^3) .* (D^5));

Ct_mean = mean(Ct_vals);
Cp_mean = mean(Cp_vals);

% Linear fit of Thrust (g) vs RPM^2: T = k_T * RPM^2
k_T = (RPM(valid).^2) \ Thrust_g(valid);

% Quadratic polynomial fit of Thrust (g) vs PWM_us
p_pwm = polyfit(PWM, Thrust_g, 2);
pwm_fine = linspace(min(PWM), max(PWM), 200);

% Loaded Motor Kv (RPM / Volt) & Kt (Nm / Amp estimate)
Kv_loaded = mean(RPM(valid) ./ Volt(valid));
Kt_est    = 60 / (2 * pi * Kv_loaded);  % Ideal electromechanical relation (Nm/A)

fprintf('=== PROPULSION SUMMARY REPORT ===\n');
fprintf('Propeller Diameter : %.1f in (%.3f m)\n', D_inch, D);
fprintf('Mean Thrust Coeff  : Ct = %.4f\n', Ct_mean);
fprintf('Mean Power Coeff   : Cp = %.4f (Electrical)\n', Cp_mean);
fprintf('Loaded Motor Kv    : %.1f RPM/V\n', Kv_loaded);
fprintf('Est. Torque Const  : Kt = %.4f N*m/A\n', Kt_est);
fprintf('Peak Thrust        : %.1f g (%.2f N) at %d us\n', max(Thrust_g), max(Thrust_N), max(PWM));
fprintf('Peak Efficiency    : %.2f g/W\n', max(g_per_W));

% --- 4. 4-PANEL ENGINEERING PLOTS ---
figure('Name', 'Propeller Dyna Pro - Aero & Motor Characterization', 'Color', 'w', 'Position', [100 100 1100 750]);

% Plot 1: Thrust vs Throttle PWM (Quadratic Fit)
subplot(2,2,1);
plot(PWM, Thrust_g, 'ko', 'MarkerFaceColor', '#007acc', 'MarkerSize', 7); hold on;
plot(pwm_fine, polyval(p_pwm, pwm_fine), 'r-', 'LineWidth', 1.8);
grid on; xlabel('Throttle PWM (\mus)'); ylabel('Thrust (g)');
title('Thrust vs. Throttle Command (Quadratic Fit)');
legend('Measured Step Avg', 'Quadratic Fit', 'Location', 'northwest');

% Plot 2: Thrust vs RPM^2 (Aerodynamic Linearity Check)
subplot(2,2,2);
rpm_sq = (RPM(valid) / 1000).^2; % (kRPM)^2 for clean axis numbers
plot(rpm_sq, Thrust_g(valid), 'ks', 'MarkerFaceColor', '#28a745', 'MarkerSize', 7); hold on;
plot(rpm_sq, k_T * (RPM(valid).^2), 'k--', 'LineWidth', 1.8);
grid on; xlabel('Motor Speed Squared (kRPM^2)'); ylabel('Thrust (g)');
title(sprintf('Aerodynamic Scaling: T \\propto RPM^2 (C_T \\approx %.4f)', Ct_mean));
legend('Measured Data', 'Linear RPM^2 Fit', 'Location', 'northwest');

% Plot 3: Specific Thrust Efficiency (g/W) vs Thrust (g)
subplot(2,2,3);
plot(Thrust_g(valid), g_per_W(valid), '-o', 'Color', '#d9534f', 'MarkerFaceColor', '#d9534f', 'LineWidth', 1.8);
grid on; xlabel('Thrust Output (g)'); ylabel('Efficiency (g / W)');
title('Propulsion Efficiency Curve (g/W vs. Thrust)');

% Plot 4: Electrical Power (W) & Current (A) vs RPM
subplot(2,2,4);
yyaxis left;
plot(RPM(valid), Power_W(valid), '-o', 'LineWidth', 1.8);
ylabel('Electrical Power (W)');
yyaxis right;
plot(RPM(valid), Curr(valid), '--s', 'LineWidth', 1.8);
ylabel('Current Draw (A)');
grid on; xlabel('Motor Speed (RPM)');
title(sprintf('Power & Current Demand (Loaded K_v \\approx %.0f RPM/V)', Kv_loaded));