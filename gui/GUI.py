#
# Interrupt Latency Monitor - Main GUI Application
# Visualizes all framework features in a modular structure
#

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import csv
import os
from typing import Dict, List, Optional
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np

# Import modules
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from driver_interface import DriverInterface
    from statistics_processor import StatisticsProcessor
    from policy_engine import PolicyEngine, Recommendation
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure all modules are in the same directory")
    sys.exit(1)


class StatisticsPanel(ttk.Frame):
    """Statistics display panel"""
    
    def __init__(self, parent, stats_processor: StatisticsProcessor):
        super().__init__(parent)
        self.stats_processor = stats_processor
        self.setup_ui()
    
    def setup_ui(self):
        """Build the UI"""
        # CPU selection
        cpu_frame = ttk.Frame(self)
        cpu_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(cpu_frame, text="CPU:").pack(side=tk.LEFT, padx=5)
        self.cpu_var = tk.StringVar(value="All")
        self.cpu_combo = ttk.Combobox(cpu_frame, textvariable=self.cpu_var, 
                                      state="readonly", width=10)
        self.cpu_combo.pack(side=tk.LEFT, padx=5)
        
        # Statistics text widget
        self.stats_text = tk.Text(self, height=20, width=80, font=("Courier", 9))
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.stats_text.yview)
        self.stats_text.configure(yscrollcommand=scrollbar.set)
        
        self.stats_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
    
    def update_statistics(self, cpu_list: List[int]):
        """Update statistics"""
        # Update CPU list
        current = self.cpu_var.get()
        self.cpu_combo['values'] = ["All"] + [str(cpu) for cpu in sorted(cpu_list)]
        if current in self.cpu_combo['values']:
            self.cpu_var.set(current)
        elif cpu_list:
            self.cpu_var.set("All")
        
        # Get selected CPU
        selected_cpu = self.cpu_var.get()
        
        self.stats_text.delete(1.0, tk.END)
        
        if selected_cpu == "All":
            all_stats = self.stats_processor.get_all_statistics()
            for cpu in sorted(all_stats.keys()):
                self._display_cpu_stats(cpu, all_stats[cpu])
        else:
            cpu = int(selected_cpu)
            stats = self.stats_processor.get_statistics(cpu)
            if stats:
                self._display_cpu_stats(cpu, stats)
    
    def _display_cpu_stats(self, cpu: int, stats: Dict):
        """Display CPU statistics"""
        self.stats_text.insert(tk.END, f"\n{'='*70}\n")
        self.stats_text.insert(tk.END, f"CPU {cpu} Statistics\n")
        self.stats_text.insert(tk.END, f"{'='*70}\n\n")
        
        self.stats_text.insert(tk.END, f"Total Events:      {stats.get('total_events', 0):>12}\n")
        self.stats_text.insert(tk.END, f"Lost Events:       {stats.get('lost_events', 0):>12}\n")
        self.stats_text.insert(tk.END, f"ISR Count:         {stats.get('isr_count', 0):>12}\n")
        self.stats_text.insert(tk.END, f"DPC Count:         {stats.get('dpc_count', 0):>12}\n")
        
        if stats.get('min_latency') is not None:
            self.stats_text.insert(tk.END, f"\nEnd-to-End Latency:\n")
            self.stats_text.insert(tk.END, f"  Min:             {stats.get('min_latency_us', 0):>10.2f} us\n")
            self.stats_text.insert(tk.END, f"  Max:             {stats.get('max_latency_us', 0):>10.2f} us\n")
            self.stats_text.insert(tk.END, f"  Average:         {stats.get('avg_latency_us', 0):>10.2f} us\n")
            self.stats_text.insert(tk.END, f"  Std Dev:         {stats.get('std_dev_us', 0):>10.2f} us\n")
            self.stats_text.insert(tk.END, f"  P50 (Median):    {stats.get('p50_us', 0):>10.2f} us\n")
            self.stats_text.insert(tk.END, f"  P95:             {stats.get('p95_us', 0):>10.2f} us\n")
            self.stats_text.insert(tk.END, f"  P99:             {stats.get('p99_us', 0):>10.2f} us\n")
            self.stats_text.insert(tk.END, f"  EWMA:            {stats.get('ewma_us', 0):>10.2f} us\n")
            
            if stats.get('anomaly_detected', False):
                self.stats_text.insert(tk.END, f"\n  *** ANOMALY DETECTED ***\n")
                self.stats_text.insert(tk.END, f"  CUSUM:           {stats.get('cusum', 0.0):>10.2f}\n")
        
        self.stats_text.insert(tk.END, "\n")


class GraphPanel(ttk.Frame):
    """Graph display panel"""
    
    def __init__(self, parent, stats_processor: StatisticsProcessor):
        super().__init__(parent)
        self.stats_processor = stats_processor
        self.setup_ui()
        self.latency_history = {}  # cpu -> list of (time, latency) tuples
        self.max_history = 100
    
    def setup_ui(self):
        """Build the UI"""
        # Graph type selection
        graph_frame = ttk.Frame(self)
        graph_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(graph_frame, text="Graph Type:").pack(side=tk.LEFT, padx=5)
        self.graph_type_var = tk.StringVar(value="Latency Over Time")
        graph_types = ["Latency Over Time", "Latency Distribution", "CPU Comparison"]
        self.graph_combo = ttk.Combobox(graph_frame, textvariable=self.graph_type_var,
                                       values=graph_types, state="readonly", width=20)
        self.graph_combo.pack(side=tk.LEFT, padx=5)
        
        # Matplotlib figure
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.ax = self.fig.add_subplot(111)
    
    def update_graph(self):
        """Update the graph"""
        graph_type = self.graph_type_var.get()
        all_stats = self.stats_processor.get_all_statistics()
        
        self.ax.clear()
        current_time = time.time()
        
        if graph_type == "Latency Over Time":
            self._plot_latency_over_time(all_stats, current_time)
        elif graph_type == "Latency Distribution":
            self._plot_latency_distribution(all_stats)
        elif graph_type == "CPU Comparison":
            self._plot_cpu_comparison(all_stats)
        
        self.fig.tight_layout()
        self.canvas.draw()
    
    def _plot_latency_over_time(self, all_stats: Dict, current_time: float):
        """Latency over time plot"""
        for cpu, stats in all_stats.items():
            if cpu not in self.latency_history:
                self.latency_history[cpu] = []
            
            if stats.get('avg_latency_us', 0) > 0:
                self.latency_history[cpu].append((current_time, stats.get('avg_latency_us', 0)))
                
                # Keep only last max_history points
                if len(self.latency_history[cpu]) > self.max_history:
                    self.latency_history[cpu] = self.latency_history[cpu][-self.max_history:]
                
                if len(self.latency_history[cpu]) > 1:
                    times = [t - self.latency_history[cpu][0][0] for t, _ in self.latency_history[cpu]]
                    latencies = [lat for _, lat in self.latency_history[cpu]]
                    self.ax.plot(times, latencies, label=f"CPU {cpu}", marker='o', markersize=3)
        
        self.ax.set_xlabel("Time (seconds)")
        self.ax.set_ylabel("Average Latency (microseconds)")
        self.ax.set_title("Latency Over Time")
        self.ax.legend()
        self.ax.grid(True, alpha=0.3)
    
    def _plot_latency_distribution(self, all_stats: Dict):
        """Latency distribution plot"""
        for cpu, stats in all_stats.items():
            latencies = stats.get('end_to_end_latencies', [])
            if latencies and len(latencies) > 0:
                # Convert to microseconds
                perf_freq = self.stats_processor.perf_frequency
                latencies_us = [(l * 1000000.0) / perf_freq for l in latencies[-1000:]]  # Last 1000
                self.ax.hist(latencies_us, bins=50, alpha=0.6, label=f"CPU {cpu}")
        
        self.ax.set_xlabel("Latency (microseconds)")
        self.ax.set_ylabel("Frequency")
        self.ax.set_title("Latency Distribution")
        self.ax.legend()
        self.ax.grid(True, alpha=0.3)
    
    def _plot_cpu_comparison(self, all_stats: Dict):
        """Per-CPU comparison plot"""
        cpus = sorted(all_stats.keys())
        p95_values = [all_stats[cpu].get('p95_us', 0) for cpu in cpus]
        p99_values = [all_stats[cpu].get('p99_us', 0) for cpu in cpus]
        
        x = np.arange(len(cpus))
        width = 0.35
        
        self.ax.bar(x - width/2, p95_values, width, label='P95', alpha=0.8)
        self.ax.bar(x + width/2, p99_values, width, label='P99', alpha=0.8)
        
        self.ax.set_xlabel("CPU")
        self.ax.set_ylabel("Latency (microseconds)")
        self.ax.set_title("CPU Latency Comparison (P95 vs P99)")
        self.ax.set_xticks(x)
        self.ax.set_xticklabels([f"CPU {cpu}" for cpu in cpus])
        self.ax.legend()
        self.ax.grid(True, alpha=0.3, axis='y')


class AnomalyPanel(ttk.Frame):
    """Anomaly detection panel"""
    
    def __init__(self, parent, stats_processor: StatisticsProcessor):
        super().__init__(parent)
        self.stats_processor = stats_processor
        self.setup_ui()
    
    def setup_ui(self):
        """Build the UI"""
        # Anomaly status
        status_frame = ttk.LabelFrame(self, text="Anomaly Status", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.anomaly_text = tk.Text(status_frame, height=15, width=60, font=("Courier", 9))
        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.anomaly_text.yview)
        self.anomaly_text.configure(yscrollcommand=scrollbar.set)
        
        self.anomaly_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def update_anomalies(self):
        """Update anomaly status"""
        self.anomaly_text.delete(1.0, tk.END)
        
        all_stats = self.stats_processor.get_all_statistics()
        
        for cpu, stats in sorted(all_stats.items()):
            if stats.get('anomaly_detected', False):
                self.anomaly_text.insert(tk.END, f"CPU {cpu}: *** ANOMALY DETECTED ***\n", "error")
                self.anomaly_text.insert(tk.END, f"  CUSUM: {stats.get('cusum', 0.0):.2f}\n")
                self.anomaly_text.insert(tk.END, f"  P99 Latency: {stats.get('p99_us', 0.0):.2f} us\n")
                self.anomaly_text.insert(tk.END, f"  EWMA: {stats.get('ewma_us', 0.0):.2f} us\n")
                self.anomaly_text.insert(tk.END, "\n")
            else:
                self.anomaly_text.insert(tk.END, f"CPU {cpu}: Normal\n", "normal")
                self.anomaly_text.insert(tk.END, f"  CUSUM: {stats.get('cusum', 0.0):.2f}\n")
                self.anomaly_text.insert(tk.END, "\n")
        
        # Configure tags
        self.anomaly_text.tag_config("error", foreground="red", font=("Courier", 9, "bold"))
        self.anomaly_text.tag_config("normal", foreground="green")


class RecommendationsPanel(ttk.Frame):
    """Recommendations panel"""
    
    def __init__(self, parent, policy_engine: PolicyEngine):
        super().__init__(parent)
        self.policy_engine = policy_engine
        self.setup_ui()
    
    def setup_ui(self):
        """Build the UI"""
        # Recommendations list
        list_frame = ttk.LabelFrame(self, text="Recommendations", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Treeview for recommendations
        columns = ("Type", "Description", "Priority")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Solution details
        detail_frame = ttk.LabelFrame(self, text="Solution Options", padding=10)
        detail_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.solution_text = tk.Text(detail_frame, height=8, width=60, font=("Courier", 9))
        solution_scrollbar = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, 
                                          command=self.solution_text.yview)
        self.solution_text.configure(yscrollcommand=solution_scrollbar.set)
        
        self.solution_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        solution_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_selection)
    
    def update_recommendations(self, recommendations: List[Recommendation]):
        """Update recommendations"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add recommendations
        for rec in recommendations:
            priority_text = ["High", "Medium", "Low"][rec.priority - 1]
            self.tree.insert("", tk.END, values=(rec.type, rec.description, priority_text),
                           tags=(priority_text.lower(),))
        
        # Configure tags for priority colors
        self.tree.tag_configure("high", foreground="red")
        self.tree.tag_configure("medium", foreground="orange")
        self.tree.tag_configure("low", foreground="blue")
    
    def on_selection(self, event):
        """Show solution options when selection changes"""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = self.tree.item(selection[0])
        rec_type = item['values'][0]
        
        self.solution_text.delete(1.0, tk.END)
        solutions = self.policy_engine.get_solution_options(rec_type)
        
        if solutions:
            self.solution_text.insert(tk.END, f"Solution options for {rec_type}:\n\n")
            for i, solution in enumerate(solutions, 1):
                self.solution_text.insert(tk.END, f"{i}. {solution}\n")
        else:
            self.solution_text.insert(tk.END, "No solution options available.")


class ConfigurationPanel(ttk.Frame):
    """Configuration panel"""
    
    def __init__(self, parent, driver_interface: DriverInterface):
        super().__init__(parent)
        self.driver_interface = driver_interface
        self.setup_ui()
    
    def setup_ui(self):
        """Build the UI"""
        config_frame = ttk.LabelFrame(self, text="Driver Configuration", padding=10)
        config_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Enable instrumentation
        self.enable_instr_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(config_frame, text="Enable Instrumentation",
                       variable=self.enable_instr_var).pack(anchor=tk.W, pady=2)
        
        # Use RDTSC
        self.use_rdtsc_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(config_frame, text="Use RDTSC (if invariant TSC available)",
                       variable=self.use_rdtsc_var).pack(anchor=tk.W, pady=2)
        
        # Sampling rate
        sampling_frame = ttk.Frame(config_frame)
        sampling_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(sampling_frame, text="Sampling Rate:").pack(side=tk.LEFT, padx=5)
        self.sampling_rate_var = tk.StringVar(value="1")
        sampling_combo = ttk.Combobox(sampling_frame, textvariable=self.sampling_rate_var,
                                     values=["1", "10", "100", "1000"], width=10, state="readonly")
        sampling_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(sampling_frame, text="(1 = every event, N = every Nth event)").pack(side=tk.LEFT, padx=5)
        
        # Apply button
        ttk.Button(config_frame, text="Apply Configuration", 
                  command=self.apply_config).pack(pady=10)
        
        # Connection status
        self.status_label = ttk.Label(config_frame, text="Status: Not Connected", 
                                     foreground="red")
        self.status_label.pack(pady=5)
    
    def apply_config(self):
        """Apply configuration"""
        if not self.driver_interface.connected:
            messagebox.showerror("Error", "Not connected to driver!")
            return
        
        try:
            sampling_rate = int(self.sampling_rate_var.get())
            success = self.driver_interface.set_config(
                enable_instrumentation=self.enable_instr_var.get(),
                use_rdtsc=self.use_rdtsc_var.get(),
                sampling_rate=sampling_rate
            )
            
            if success:
                messagebox.showinfo("Success", "Configuration applied successfully!")
            else:
                messagebox.showerror("Error", "Failed to apply configuration!")
        except Exception as e:
            messagebox.showerror("Error", f"Error applying configuration: {e}")
    
    def update_status(self, connected: bool):
        """Update connection status"""
        if connected:
            self.status_label.config(text="Status: Connected", foreground="green")
        else:
            self.status_label.config(text="Status: Not Connected", foreground="red")


class InterruptLatencyMonitorGUI:
    """Main GUI application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Interrupt Latency Monitor")
        self.root.geometry("1400x900")
        
        # Initialize modules
        self.driver_interface = DriverInterface()
        self.stats_processor = StatisticsProcessor()
        self.policy_engine = PolicyEngine()
        
        # Collection thread
        self.collection_running = False
        self.collection_thread = None
        
        # Setup UI
        self.setup_menu()
        self.setup_toolbar()
        self.setup_main_panel()
        
        # Start update loop
        self.update_interval = 1000  # ms
        self.update_ui()
    
    def setup_menu(self):
        """Build the menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Connect to Driver", command=self.connect_driver)
        file_menu.add_command(label="Disconnect", command=self.disconnect_driver)
        file_menu.add_separator()
        file_menu.add_command(label="Export to CSV", command=self.export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Reset Statistics", command=self.reset_statistics)
        tools_menu.add_command(label="Reset Buffers", command=self.reset_buffers)
    
    def setup_toolbar(self):
        """Build the toolbar"""
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # Connection buttons
        ttk.Button(toolbar, text="Connect", command=self.connect_driver).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Disconnect", command=self.disconnect_driver).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Collection control
        self.collection_var = tk.BooleanVar()
        self.collection_check = ttk.Checkbutton(toolbar, text="Enable Collection",
                                                variable=self.collection_var,
                                                command=self.toggle_collection)
        self.collection_check.pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Status
        self.status_label = ttk.Label(toolbar, text="Status: Not Connected", foreground="red")
        self.status_label.pack(side=tk.LEFT, padx=10)
    
    def setup_main_panel(self):
        """Build the main panel"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Statistics tab
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="Statistics")
        self.stats_panel = StatisticsPanel(stats_frame, self.stats_processor)
        self.stats_panel.pack(fill=tk.BOTH, expand=True)
        
        # Graphs tab
        graph_frame = ttk.Frame(notebook)
        notebook.add(graph_frame, text="Graphs")
        self.graph_panel = GraphPanel(graph_frame, self.stats_processor)
        self.graph_panel.pack(fill=tk.BOTH, expand=True)
        
        # Anomaly tab
        anomaly_frame = ttk.Frame(notebook)
        notebook.add(anomaly_frame, text="Anomaly Detection")
        self.anomaly_panel = AnomalyPanel(anomaly_frame, self.stats_processor)
        self.anomaly_panel.pack(fill=tk.BOTH, expand=True)
        
        # Recommendations tab
        rec_frame = ttk.Frame(notebook)
        notebook.add(rec_frame, text="Recommendations")
        self.rec_panel = RecommendationsPanel(rec_frame, self.policy_engine)
        self.rec_panel.pack(fill=tk.BOTH, expand=True)
        
        # Configuration tab
        config_frame = ttk.Frame(notebook)
        notebook.add(config_frame, text="Configuration")
        self.config_panel = ConfigurationPanel(config_frame, self.driver_interface)
        self.config_panel.pack(fill=tk.BOTH, expand=True)
    
    def connect_driver(self):
        """Connect to the driver"""
        if self.driver_interface.connect():
            self.status_label.config(text="Status: Connected", foreground="green")
            self.config_panel.update_status(True)
            messagebox.showinfo("Success", "Connected to driver successfully!")
        else:
            self.status_label.config(text="Status: Connection Failed", foreground="red")
            messagebox.showerror("Error", "Failed to connect to driver!\n\n"
                                "Make sure:\n"
                                "1. Driver is loaded (sc query InterruptLatencyMonitor)\n"
                                "2. Running as administrator\n"
                                "3. Driver is properly installed")
    
    def disconnect_driver(self):
        """Disconnect from the driver"""
        self.toggle_collection(False)
        self.driver_interface.disconnect()
        self.status_label.config(text="Status: Disconnected", foreground="red")
        self.config_panel.update_status(False)
    
    def toggle_collection(self, enable=None):
        """Toggle event collection on/off"""
        if enable is None:
            enable = self.collection_var.get()
        else:
            self.collection_var.set(enable)
        
        if enable and self.driver_interface.connected:
            if not self.collection_running:
                self.collection_running = True
                self.collection_thread = threading.Thread(target=self.collection_loop, daemon=True)
                self.collection_thread.start()
        else:
            self.collection_running = False
    
    def collection_loop(self):
        """Event collection loop (background thread)"""
        import platform
        
        # Get CPU count
        cpu_count = os.cpu_count() or 1
        
        while self.collection_running and self.driver_interface.connected:
            try:
                for cpu in range(cpu_count):
                    if not self.collection_running:
                        break
                    
                    events = self.driver_interface.get_events(cpu, max_events=1000)
                    if events:
                        self.stats_processor.process_events(cpu, events)
                
                time.sleep(0.1)  # 100ms interval
            except Exception as e:
                print(f"Collection error: {e}")
                time.sleep(1.0)
    
    def update_ui(self):
        """Update the UI"""
        if self.driver_interface.connected:
            # Get all CPU statistics
            all_stats = self.stats_processor.get_all_statistics()
            cpu_list = list(all_stats.keys()) if all_stats else []
            
            # Update panels
            self.stats_panel.update_statistics(cpu_list)
            self.graph_panel.update_graph()
            self.anomaly_panel.update_anomalies()
            
            # Update recommendations
            recommendations = self.policy_engine.analyze(all_stats)
            self.rec_panel.update_recommendations(recommendations)
        
        # Schedule next update
        self.root.after(self.update_interval, self.update_ui)
    
    def reset_statistics(self):
        """Reset statistics"""
        if messagebox.askyesno("Confirm", "Reset all statistics?"):
            self.stats_processor.reset()
    
    def reset_buffers(self):
        """Reset ring buffers"""
        if not self.driver_interface.connected:
            messagebox.showerror("Error", "Not connected to driver!")
            return
        
        if messagebox.askyesno("Confirm", "Reset all ring buffers in driver?"):
            if self.driver_interface.reset_buffers():
                messagebox.showinfo("Success", "Buffers reset successfully!")
            else:
                messagebox.showerror("Error", "Failed to reset buffers!")
    
    def export_csv(self):
        """Export to CSV"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            all_stats = self.stats_processor.get_all_statistics()
            
            with open(filename, 'w', newline='') as csvfile:
                fieldnames = ['CPU', 'TotalEvents', 'LostEvents', 'ISRCount', 'DPCCount',
                            'MinLatency_us', 'MaxLatency_us', 'AvgLatency_us', 'StdDev_us',
                            'P50_us', 'P95_us', 'P99_us', 'EWMA_us', 'AnomalyDetected']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for cpu in sorted(all_stats.keys()):
                    stats = all_stats[cpu]
                    writer.writerow({
                        'CPU': cpu,
                        'TotalEvents': stats.get('total_events', 0),
                        'LostEvents': stats.get('lost_events', 0),
                        'ISRCount': stats.get('isr_count', 0),
                        'DPCCount': stats.get('dpc_count', 0),
                        'MinLatency_us': stats.get('min_latency_us', 0.0),
                        'MaxLatency_us': stats.get('max_latency_us', 0.0),
                        'AvgLatency_us': stats.get('avg_latency_us', 0.0),
                        'StdDev_us': stats.get('std_dev_us', 0.0),
                        'P50_us': stats.get('p50_us', 0.0),
                        'P95_us': stats.get('p95_us', 0.0),
                        'P99_us': stats.get('p99_us', 0.0),
                        'EWMA_us': stats.get('ewma_us', 0.0),
                        'AnomalyDetected': 1 if stats.get('anomaly_detected', False) else 0
                    })
            
            messagebox.showinfo("Success", f"Statistics exported to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")
    
    def on_closing(self):
        """Application closing handler"""
        self.collection_running = False
        if self.collection_thread:
            self.collection_thread.join(timeout=2.0)
        self.driver_interface.disconnect()
        self.root.destroy()


def main():
    """Main entry point"""
    root = tk.Tk()
    app = InterruptLatencyMonitorGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()

