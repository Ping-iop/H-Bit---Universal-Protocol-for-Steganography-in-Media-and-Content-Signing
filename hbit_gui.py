"""
H-Bit Desktop App - Notario Digital
===================================
Interfaz gráfica moderna para firmar y verificar archivos H-Bit.
"""

import os
import sys
import threading
import time
from pathlib import Path
from datetime import datetime
import customtkinter as ctk
from PIL import Image

# Configurar path para importar hbit
sys.path.append(str(Path(__file__).parent / "src"))

try:
    from hbit.universal import UniversalVerifier, UniversalEncoder, UniversalVerifyResult, UniversalVerificationStatus as VerificationStatus
    from hbit.core.crypto import HBitKeyPair, generate_key_pair
except ImportError as e:
    print(f"Error importando H-Bit Core: {e}")
    sys.exit(1)

# Configuración UI
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class HBitApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configuración Ventana
        self.title("H-Bit Notary | Sistema de Autenticidad Digital")
        self.geometry("900x600")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=10)
        self.grid_rowconfigure(1, weight=1) # Espacio para consola

        # Estado
        self.current_key = None
        self.key_path = Path("identity/my_key")
        self.load_identity()

        # Componentes
        self.create_sidebar()
        self.create_main_view()
        self.create_console()

    def create_console(self):
        self.console_frame = ctk.CTkFrame(self, height=150, corner_radius=0)
        self.console_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        
        lbl = ctk.CTkLabel(self.console_frame, text="Log de Operaciones:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl.pack(anchor="w", padx=10, pady=(5,0))
        
        self.console_log = ctk.CTkTextbox(self.console_frame, height=120, font=ctk.CTkFont(family="Consolas", size=12))
        self.console_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.console_log.configure(state="disabled")

    def log(self, message):
        """Escribe en la consola de la GUI de forma segura para threads."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {message}\n"
        print(message) # También a stdout real
        self.after(0, lambda: self._write_log(full_msg))

    def _write_log(self, msg):
        self.console_log.configure(state="normal")
        self.console_log.insert("end", msg)
        self.console_log.see("end")
        self.console_log.configure(state="disabled")

    def load_identity(self):
        """Carga la identidad por defecto si existe."""
        if self.key_path.exists() and self.key_path.is_dir():
            try:
                self.current_key = HBitKeyPair.load_from_directory(self.key_path)
                # No podemos loggear antes de crear la consola, pero guardamos
            except:
                pass

    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", rowspan=1) # Rowspan 1 para no tapar consola
        self.sidebar.grid_rowconfigure(4, weight=1)

        logo = ctk.CTkLabel(self.sidebar, text="H-BIT\nSECURE OS", font=ctk.CTkFont(size=20, weight="bold"))
        logo.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.btn_dashboard = ctk.CTkButton(self.sidebar, text="Verificar / Firmar", command=self.show_dashboard)
        self.btn_dashboard.grid(row=1, column=0, padx=20, pady=10)

        self.btn_identity = ctk.CTkButton(self.sidebar, text="Mi Identidad", command=self.show_identity)
        self.btn_identity.grid(row=2, column=0, padx=20, pady=10)

        # self.btn_history = ctk.CTkButton(self.sidebar, text="Historial", command=self.show_history)
        # self.btn_history.grid(row=3, column=0, padx=20, pady=10)

        # Accelerator Status
        from hbit.core.accelerator import xp
        backend_name = "GPU (CUDA)" if xp.__name__ == "cupy" else "CPU (NumPy)"
        color = "#2ecc71" if xp.__name__ == "cupy" else "gray"
        
        accel_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        accel_frame.grid(row=5, column=0, padx=20, pady=(10, 0))
        ctk.CTkLabel(accel_frame, text="Acelerador:", font=ctk.CTkFont(size=12)).pack(anchor="w")
        ctk.CTkLabel(accel_frame, text=backend_name, text_color=color, font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")

        version = ctk.CTkLabel(self.sidebar, text="v2.2 GUI", text_color="gray")
        version.grid(row=6, column=0, padx=20, pady=20)

    def create_main_view(self):
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.show_dashboard()

    def clear_main(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def show_dashboard(self):
        self.clear_main()
        
        # Header
        header = ctk.CTkLabel(self.main_frame, text="Verificación de Archivos", font=ctk.CTkFont(size=24, weight="bold"))
        header.pack(pady=20, anchor="w")

        # Drop Zone (Simulada con botón grande)
        self.drop_zone = ctk.CTkButton(
            self.main_frame, 
            text="📁 Seleccionar Archivo para Analizar\n(Soporta Drag & Drop en futuro)", 
            font=ctk.CTkFont(size=18),
            height=150,
            fg_color="transparent",
            border_width=2,
            border_color=("gray70", "gray30"),
            text_color=("gray10", "gray90"),
            hover_color=("gray80", "gray20"),
            command=self.select_file
        )
        self.drop_zone.pack(fill="x", pady=20)

        # Result Area
        self.result_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.result_frame.pack(fill="both", expand=True)

    def show_identity(self):
        self.clear_main()
        header = ctk.CTkLabel(self.main_frame, text="Gestión de Identidad", font=ctk.CTkFont(size=24, weight="bold"))
        header.pack(pady=20, anchor="w")

        info_frame = ctk.CTkFrame(self.main_frame)
        info_frame.pack(fill="x", pady=20, padx=10)

        if self.current_key:
            ctk.CTkLabel(info_frame, text="Identidad Activa:", font=ctk.CTkFont(weight="bold")).pack(pady=(10,5))
            fingerprint = self.current_key.public_key_hex[:16] + "..."
            ctk.CTkLabel(info_frame, text=f"Fingerprint: {fingerprint}", text_color="cyan").pack(pady=5)
            ctk.CTkLabel(info_frame, text="Esta identidad se usará para firmar nuevos archivos.").pack(pady=(5,10))
        else:
            ctk.CTkLabel(info_frame, text="No tienes una identidad cargada.", text_color="orange").pack(pady=10)
            btn_gen = ctk.CTkButton(info_frame, text="Generar Nueva Identidad", command=self.generate_identity)
            btn_gen.pack(pady=10)

    def show_history(self):
        pass

    def generate_identity(self):
        # Generar key
        if not self.key_path.parent.exists():
            os.makedirs(self.key_path.parent)
        
        self.log("Generando nueva par de claves Ed25519...")
        self.current_key = generate_key_pair()
        self.current_key.save_to_directory(self.key_path)
        self.log(f"Identidad guardada en: {self.key_path}")
        self.show_identity()

    def select_file(self):
        file_path = ctk.filedialog.askopenfilename()
        if file_path:
            self.show_file_actions(file_path)

    def show_file_actions(self, file_path):
        self.clear_main()
        
        # Header
        header = ctk.CTkLabel(self.main_frame, text="Acción Requerida", font=ctk.CTkFont(size=24, weight="bold"))
        header.pack(pady=20, anchor="w")

        # File Info
        file_card = ctk.CTkFrame(self.main_frame, fg_color="gray20", corner_radius=10)
        file_card.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(file_card, text="Archivo Seleccionado:", font=ctk.CTkFont(size=14)).pack(pady=(10,5))
        ctk.CTkLabel(file_card, text=Path(file_path).name, font=ctk.CTkFont(size=16, weight="bold"), text_color="cyan").pack(pady=(0,10))

        # Action Buttons
        actions_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        actions_frame.pack(fill="both", expand=True, pady=20)

        # Botón Verificar
        btn_verify = ctk.CTkButton(
            actions_frame, 
            text="🔍 Verificar Autenticidad", 
            font=ctk.CTkFont(size=18),
            height=60,
            fg_color="#2980b9",
            hover_color="#3498db",
            command=lambda: self.process_file(file_path)
        )
        btn_verify.pack(fill="x", padx=20, pady=10)

        # Botón Firmar
        btn_sign = ctk.CTkButton(
            actions_frame, 
            text="✍️ Firmar Digitalmente", 
            font=ctk.CTkFont(size=18),
            height=60,
            fg_color="#f39c12",
            hover_color="#f1c40f",
            text_color="black",
            command=lambda: self.initiate_signing(file_path)
        )
        btn_sign.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(actions_frame, text="Firmar verificará primero si el archivo ya tiene una firma.", text_color="gray").pack()

    def initiate_signing(self, file_path):
        # Primero verificamos si ya tiene firma
        for widget in self.main_frame.winfo_children():
            widget.destroy()

        # Recreamos result_frame si fue destruido por clear_main
        self.result_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.result_frame.pack(fill="both", expand=True)

        loading = ctk.CTkLabel(self.result_frame, text="Verificando estado previo...", text_color="gray")
        loading.pack(pady=20)
        self.log("Verificando existencia de firma previa...")
        
        threading.Thread(target=self._check_sig_and_sign, args=(file_path,), daemon=True).start()

    def _check_sig_and_sign(self, file_path):
        verifier = UniversalVerifier()
        result = verifier.verify(file_path)
        self.after(0, lambda: self._handle_pre_sign_result(file_path, result))

    def _handle_pre_sign_result(self, file_path, result):
        if result.status == VerificationStatus.NOT_FOUND:
            self.log("Archivo limpio. Procediendo a firma.")
            self.sign_file_dialog(file_path)
        else:
            self.log(f"El archivo ya está firmado/alterado: {result.status.name}")
            self.show_result(file_path, result)
            ctk.CTkLabel(self.result_frame, text="⚠ Este archivo ya contiene datos H-Bit. No se puede firmar sobre una firma.", text_color="orange").pack(pady=5)

    def process_file(self, file_path):
        # Asegurar un estado limpio de la UI
        self.clear_main()
        self.result_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.result_frame.pack(fill="both", expand=True)

        # Spinner loading
        loading = ctk.CTkLabel(self.result_frame, text="Analizando estructura y criptografía...", text_color="gray")
        loading.pack(pady=20)
        self.log(f"Iniciando análisis de: {Path(file_path).name}")
        self.update()

        # Ejecutar en thread para no bloquear UI
        threading.Thread(target=self._run_verification, args=(file_path,), daemon=True).start()

    def _run_verification(self, file_path):
        # Verificar
        verifier = UniversalVerifier()
        # Intentar verificar sin passphrase primero
        result = verifier.verify(file_path)
        
        # Actualizar UI en main thread
        self.after(0, lambda: self.show_result(file_path, result))

    def show_result(self, file_path, result: UniversalVerifyResult):
        # Limpiar loading
        for widget in self.result_frame.winfo_children():
            widget.destroy()
            
        self.log(f"Resultado: {result.status.name} - {result.message[:50]}...")

        # Tarjeta de resultado
        card_color = "gray20"
        status_color = "gray"
        icon = "❓"

        if result.status == VerificationStatus.VERIFIED:
            card_color = "#1a4d1a" # Verde oscuro
            status_color = "#2ecc71" # Verde brillante
            icon = "✅ AUTÉNTICO"
        elif result.status == VerificationStatus.TAMPERED:
            card_color = "#4d1a1a" # Rojo oscuro
            status_color = "#e74c3c" # Rojo
            icon = "❌ MANIPULADO"
        elif result.status == VerificationStatus.NOT_FOUND:
            card_color = "gray15"
            status_color = "gray"
            icon = "⚪ SIN FIRMA"
        
        card = ctk.CTkFrame(self.result_frame, fg_color=card_color, corner_radius=10)
        card.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=30)).pack(pady=(20, 10))
        ctk.CTkLabel(card, text=result.status.name, font=ctk.CTkFont(size=16, weight="bold"), text_color=status_color).pack(pady=5)
        
        details = ctk.CTkTextbox(card, height=100, fg_color="transparent")
        details.pack(fill="x", padx=20, pady=10)
        details.insert("0.0", result.message)
        
        # FIX: Acceder a decode_result.payload
        payload = result.decode_result.payload if result.decode_result else None
        
        if payload:
            details.insert("end", f"\n\nAutor Hash: {payload.author_hash.hex()[:16]}...")
            ts = datetime.fromtimestamp(payload.timestamp)
            details.insert("end", f"\nFecha Firma: {ts}")
        
        details.configure(state="disabled")

        if result.status == VerificationStatus.NOT_FOUND:
            btn_sign = ctk.CTkButton(self.result_frame, text="Firmar este archivo (Inyectar H-Bit)", 
                                     fg_color="#f1c40f", text_color="black", hover_color="#d4ac0d",
                                     command=lambda: self.sign_file_dialog(file_path))
            btn_sign.pack(pady=10)

    def sign_file_dialog(self, input_path):
        if not self.current_key:
            self.log("Firma detenida: No hay identidad activa.")
            
            # Limpiar vista actual (estaba en loading)
            for widget in self.result_frame.winfo_children():
                widget.destroy()
                
            # Mostrar mensaje de error en la UI principal
            ctk.CTkLabel(self.result_frame, text="🔒 Identidad Requerida", font=ctk.CTkFont(size=20, weight="bold"), text_color="orange").pack(pady=(20, 10))
            ctk.CTkLabel(self.result_frame, text="Para firmar digitalmente archivos, necesitas generar o cargar una identidad criptográfica.", font=ctk.CTkFont(size=14)).pack(pady=5)
            
            ctk.CTkButton(self.result_frame, text="Ir a Gestión de Identidad", command=self.show_identity, fg_color="#e67e22", hover_color="#d35400").pack(pady=20)
            
            # Botón para volver atrás o cancelar
            ctk.CTkButton(self.result_frame, text="Cancelar", command=lambda: self.show_file_actions(input_path), fg_color="gray", hover_color="gray30").pack(pady=5)
            return

        output_path = ctk.filedialog.asksaveasfilename(initialfile=Path(input_path).name)
        if output_path:
            self.log(f"Firmando archivo hacía: {output_path}")
            threading.Thread(target=self._run_signing, args=(input_path, output_path), daemon=True).start()
        else:
            self.log("Firma cancelada.")
            self.show_file_actions(input_path)

    def _run_signing(self, input_path, output_path):
        try:
            encoder = UniversalEncoder()
            self.after(0, lambda: self.log("Iniciando motor de firma..."))
            
            encoder.encode(
                file_path=input_path,
                author_key=self.current_key, 
                output_path=output_path
            )
            self.after(0, lambda: self.log("Firma completada con éxito."))
            self.after(0, lambda: self.process_file(output_path)) 
        except Exception as e:
            self.after(0, lambda: self.log(f"ERROR FATAL: {e}"))
            print(f"Error signing: {e}")

if __name__ == "__main__":
    app = HBitApp()
    app.mainloop()
