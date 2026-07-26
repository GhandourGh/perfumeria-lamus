import re
from datetime import datetime

from babel.dates import format_date as babel_date, format_datetime as babel_datetime
from babel.numbers import format_currency
from bs4 import BeautifulSoup
SUPPORTED_LOCALES = {"es_CO": "Español (Colombia)", "en": "English"}
DEFAULT_LOCALE = "es_CO"


ES = {
    # Shell and navigation
    "Skip to content": "Saltar al contenido", "Open navigation": "Abrir navegación",
    "Primary": "Principal", "Customers": "Clientes", "Vendors": "Proveedores",
    "Overview": "Resumen", "All customers": "Todos los clientes", "New customer": "Nuevo cliente",
    "All vendors": "Todos los proveedores", "New vendor": "Nuevo proveedor", "More": "Más",
    "Bank": "Banco", "Reports": "Informes", "Backup & restore": "Copia y restauración",
    "Security": "Seguridad", "Account settings": "Configuración de la cuenta", "Backup": "Copia",
    "Sign out": "Cerrar sesión", "Back": "Volver", "Dismiss notification": "Cerrar notificación",
    "End of page": "Fin de la página", "Back to top": "Volver arriba", "Maison Ledger": "Libro de cuentas",
    "Perfumería Lamus · Maison Ledger": "Perfumería Lamus · Libro de cuentas",
    "Maison Ledger · Private": "Libro de cuentas · Privado", "English": "Inglés",
    # Authentication
    "Owner access": "Acceso del propietario", "Welcome back": "Bienvenido de nuevo",
    "Sign in to open the store ledger.": "Inicia sesión para abrir las cuentas del negocio.",
    "Username": "Usuario", "Password": "Contraseña", "Sign in": "Ingresar",
    "Forgot your password?": "¿Olvidaste tu contraseña?", "Account recovery": "Recuperación de la cuenta",
    "Recover access": "Recuperar acceso",
    "Enter the username and saved recovery code. Each code works only once.": "Ingresa el usuario y el código de recuperación guardado. Cada código funciona una sola vez.",
    "Recovery code": "Código de recuperación", "Continue securely": "Continuar de forma segura",
    "The recovery code is created from Security while signed in. Keep it outside this laptop.": "El código se crea desde Seguridad después de iniciar sesión. Guárdalo fuera de este portátil.",
    "Back to sign in": "Volver al ingreso", "Choose a new password": "Elige una contraseña nueva",
    "Choose a password you can remember and keep private.": "Elige una contraseña que puedas recordar y mantenla privada.",
    "New password": "Contraseña nueva", "Confirm new password": "Confirmar contraseña nueva",
    "Save new password": "Guardar contraseña nueva",
    "The house ledger — customer accounts, credit sales, and payments, kept in one careful book.": "Las cuentas del negocio: clientes, ventas a crédito y pagos, todo organizado en un solo lugar.",
    "Private": "Privado",
    # Common
    "Close": "Cerrar", "Cancel": "Cancelar", "Save changes": "Guardar cambios", "Edit": "Editar",
    "Open": "Abrir", "Payment": "Pago", "Statement": "Estado de cuenta", "Notes": "Notas",
    "Note:": "Nota:", "No note": "Sin nota", "No phone on file": "Sin teléfono registrado",
    "optional": "opcional", "Date": "Fecha", "Amount": "Valor", "Description": "Descripción",
    "Detail": "Detalle", "Status": "Estado", "Balance": "Saldo", "Paid": "Pagado",
    "Partial": "Parcial", "Voided": "Anulado", "Settled": "Al día", "Balance due": "Saldo pendiente",
    "Payable": "Por pagar", "All": "Todos", "Expand": "Ver más", "Collapse": "Ver menos",
    "Show all": "Ver todos", "Show less": "Ver menos", "No payments yet": "Aún no hay pagos",
    "No activity yet.": "Aún no hay movimientos.", "No account movements recorded yet.": "Aún no hay movimientos registrados.",
    "All settled": "Todo al día",
    "Add your first customer to start keeping their account in the ledger.": "Agrega tu primer cliente para comenzar a llevar su cuenta.",
    "Ledger entries will appear here as you record credit sales and payments.": "Los movimientos aparecerán aquí cuando registres ventas a crédito y pagos.",
    "No customer currently carries a balance.": "Ningún cliente tiene saldo pendiente.",
    "Add your first customer to open their account in the house ledger.": "Agrega tu primer cliente para abrir su cuenta.",
    "Vendor purchases and payments will appear here as you record them.": "Las compras y los pagos a proveedores aparecerán aquí cuando los registres.",
    # Dashboards and registries
    "Customers overview": "Resumen de clientes",
    "Customer credit, payments received, and who to follow up — at a glance.": "Créditos, pagos recibidos y clientes por gestionar, todo de un vistazo.",
    "Outstanding balance": "Saldo pendiente", "Collected today": "Cobrado hoy",
    "New credit today": "Crédito nuevo hoy", "Find a customer": "Buscar cliente",
    "Open an account to record a credit sale or payment.": "Abre una cuenta para registrar una venta a crédito o un pago.",
    "Search by name, phone, or note…": "Buscar por nombre, teléfono o nota…",
    "Customer accounts": "Cuentas de clientes", "Recent activity": "Actividad reciente",
    "Latest ledger entries": "Últimos movimientos", "Largest balances": "Saldos más altos",
    "House accounts": "Cuentas del negocio", "Bank balance": "Saldo bancario",
    "Payable to vendors": "Por pagar a proveedores", "Bank movements": "Movimientos bancarios",
    "Vendor accounts": "Cuentas de proveedores", "Add first customer": "Agregar el primer cliente",
    "Registry · Receivables": "Registro · Cuentas por cobrar", "Every account, its balance, and its last movement — ready for the counter.": "Todas las cuentas, sus saldos y su último movimiento, listas para atender.",
    "Filter customers": "Filtrar clientes", "With balance": "Con saldo", "Paid recently": "Pagaron recientemente",
    "Sort customers": "Ordenar clientes", "Sort: Largest balance": "Ordenar: saldo más alto",
    "Sort: Name A–Z": "Ordenar: nombre A–Z", "Sort: Recently active": "Ordenar: actividad reciente",
    "Sort: Recently added": "Ordenar: agregados recientemente", "Search customers": "Buscar clientes",
    "Vendor accounts": "Cuentas de proveedores", "Vendors overview": "Resumen de proveedores",
    "Stock purchased, payments sent, and what the store still owes its suppliers.": "Compras de inventario, pagos enviados y lo que el negocio todavía debe a sus proveedores.",
    "Amount owed": "Total por pagar", "Amount paid": "Total pagado",
    "Total payments sent to vendors": "Total de pagos enviados a proveedores",
    "Bancolombia · main account": "Bancolombia · cuenta principal", "Find a vendor": "Buscar proveedor",
    "Open an account to record a purchase or payment.": "Abre una cuenta para registrar una compra o un pago.",
    "Largest payables": "Cuentas por pagar más altas", "Recent vendor activity": "Actividad reciente de proveedores",
    "Latest purchases & payments": "Últimas compras y pagos", "Registry · Payables": "Registro · Cuentas por pagar",
    "Suppliers of the house — stock purchases, payments sent, and what remains payable.": "Proveedores del negocio: compras de inventario, pagos enviados y saldos pendientes.",
    "Search vendors": "Buscar proveedores", "Filter vendors": "Filtrar proveedores",
    "With payable": "Con saldo por pagar", "Sort vendors": "Ordenar proveedores",
    "Sort: Largest payable": "Ordenar: mayor saldo por pagar", "Add first vendor": "Agregar el primer proveedor",
    # Account details and forms
    "Customer account": "Cuenta del cliente", "Vendor account": "Cuenta del proveedor",
    "Account summary": "Resumen de la cuenta", "Credit taken": "Crédito otorgado",
    "Lifetime credit sales": "Total histórico de ventas a crédito", "Paid to date": "Pagado hasta hoy",
    "Payable now": "Por pagar ahora", "Purchased to date": "Comprado hasta hoy",
    "Lifetime stock purchases": "Total histórico de compras de inventario",
    "Record credit sale": "Registrar venta a crédito", "Record payment": "Registrar pago",
    "Record stock purchase": "Registrar compra de inventario", "Record payment sent": "Registrar pago enviado",
    "Sale amount": "Valor de la venta", "Purchase amount": "Valor de la compra",
    "Payment amount": "Valor del pago", "Payment method": "Medio de pago",
    "Cash": "Efectivo", "Bank transfer": "Transferencia bancaria", "Card": "Tarjeta",
    "Check": "Cheque", "Split": "Combinado", "What was sold": "Qué se vendió",
    "What was purchased": "Qué se compró", "Due date": "Fecha de vencimiento",
    "Colombian pesos, whole amounts.": "Pesos colombianos, sin decimales.",
    "When you expect this to be paid. Shown on the ledger for reference.": "Fecha esperada de pago. Se muestra como referencia en la cuenta.",
    "Balance today": "Saldo de hoy", "This credit sale": "Esta venta a crédito",
    "New balance": "Saldo nuevo", "Payable today": "Por pagar hoy", "This purchase": "Esta compra",
    "New payable": "Nuevo saldo por pagar", "This payment": "Este pago",
    "Remaining balance": "Saldo restante", "Remaining payable": "Saldo por pagar restante",
    "Add to account": "Agregar a la cuenta", "Bank transfers are also deducted from the bank balance.": "Las transferencias bancarias también se descuentan del saldo bancario.",
    "This payment is larger than the payable balance.": "Este pago supera el saldo por pagar.",
    "Reduce the amount.": "Reduce el valor.", "This account has no balance due": "Esta cuenta no tiene saldo pendiente",
    "Nothing is payable to this vendor": "No hay saldo pendiente con este proveedor",
    "Full name": "Nombre completo", "Phone": "Teléfono", "Opening balance owed": "Saldo inicial pendiente",
    "Opening amount payable": "Saldo inicial por pagar", "What for": "Concepto",
    "Payment habits, family account, preferences…": "Hábitos de pago, cuenta familiar, preferencias…",
    "Ordering details, invoice cadence…": "Detalles de pedidos, frecuencia de facturación…",
    "Previous tab": "Cuenta anterior", "Outstanding invoice": "Factura pendiente",
    "Add Customer": "Agregar cliente", "Edit Customer": "Editar cliente",
    "Add Vendor": "Agregar proveedor", "Edit Vendor": "Editar proveedor",
    # Ledger
    "Account ledger": "Movimientos de la cuenta", "Edit ledger entry": "Editar movimiento",
    "Opening balance": "Saldo inicial", "Opening purchase": "Compra inicial",
    "Correct the entry below. The account balance will be recalculated automatically.": "Corrige el movimiento. El saldo de la cuenta se recalculará automáticamente.",
    "Confirm this edit": "Confirmar esta edición",
    "This changes a financial record and recalculates the account balance.": "Esto modifica un registro financiero y recalcula el saldo de la cuenta.",
    "Ledger entry": "Movimiento de cuenta", "Go back": "Regresar", "Save edit": "Guardar edición",
    # Reports
    "Office · Print center": "Oficina · Centro de informes", "Print business overview": "Imprimir resumen del negocio",
    "Business figures": "Cifras del negocio", "Customer balances": "Saldos de clientes",
    "Vendor balances": "Saldos de proveedores", "Bank history": "Historial bancario",
    "Recent ledger activity": "Actividad reciente de cuentas", "Owner action report": "Informe de actividad del propietario",
    "OWNER REPORT": "INFORME DEL PROPIETARIO", "BU SALIM activity": "Actividad de BU SALIM",
    "From": "Desde", "To": "Hasta", "Action": "Acción", "All actions": "Todas las acciones",
    "Apply": "Aplicar", "Clear": "Limpiar", "Export CSV": "Exportar CSV",
    "Owner": "Propietario", "Account": "Cuenta", "Details": "Detalles",
    "Store / system": "Negocio / sistema", "No actions match these filters.": "No hay acciones que coincidan con estos filtros.",
    "Phone": "Teléfono", "Credit taken": "Crédito otorgado", "Balance due": "Saldo pendiente",
    "Purchased": "Comprado", "Movement": "Movimiento", "Prepared": "Preparado",
    "Print statement": "Imprimir estado de cuenta", "Back to account": "Volver a la cuenta",
    "Account history": "Historial de la cuenta", "Account settled — thank you": "Cuenta al día — gracias",
    # Bank
    "Bank account": "Cuenta bancaria", "Current balance": "Saldo actual", "Add money": "Agregar dinero",
    "Remove money": "Retirar dinero", "Set balance": "Establecer saldo", "Record movement": "Registrar movimiento",
    "Take money out": "Retirar dinero", "Office · Bancolombia": "Oficina · Bancolombia",
    "Bancolombia & suppliers": "Bancolombia y proveedores", "Heads up:": "Atención:",
    "recorded actions": "acciones registradas", "sign-ins": "ingresos",
    # Backup
    "Backup & recovery": "Copia y recuperación", "Save or restore a complete copy of the store records.": "Guarda o restaura una copia completa de los registros del negocio.",
    "MANUAL BACKUP": "COPIA MANUAL", "Save everything now": "Guardar todo ahora",
    "Downloads one complete file containing customers, vendors, ledgers, payments, bank history, users, and audit records.": "Descarga un archivo completo con clientes, proveedores, cuentas, pagos, historial bancario, usuarios y auditoría.",
    "Download backup": "Descargar copia", "FULL RESTORE": "RESTAURACIÓN COMPLETA",
    "Restore a saved backup": "Restaurar una copia guardada", "Return all store records to a previous saved copy.": "Devuelve todos los registros del negocio a una copia anterior.",
    "Backup file": "Archivo de copia", "Type RESTORE to confirm": "Escribe RESTAURAR para confirmar",
    "A safety copy is created before anything changes.": "Se crea una copia de seguridad antes de realizar cambios.",
    "Restore everything": "Restaurar todo",
    # Security
    "OWNER SETTINGS": "CONFIGURACIÓN DEL PROPIETARIO", "Protect the owner account and prepare a safe way back in.": "Protege la cuenta del propietario y prepara una forma segura de recuperar el acceso.",
    "SAVE THIS NOW": "GUARDA ESTO AHORA", "Your one-time recovery code": "Tu código de recuperación de un solo uso",
    "Write it on paper or save it on a USB drive. It will not be shown again.": "Anótalo en papel o guárdalo en una memoria USB. No volverá a mostrarse.",
    "PASSWORD": "CONTRASEÑA", "Change password": "Cambiar contraseña", "Current password": "Contraseña actual",
    "Use 8 or more characters.": "Usa 8 caracteres o más.", "RECOVERY": "RECUPERACIÓN",
    "Create recovery code": "Crear código de recuperación", "Replace recovery code": "Reemplazar código de recuperación",
    "Language": "Idioma",
    "This will take the bank balance to {amount}. Record it anyway?": "Esto dejará el saldo bancario en {amount}. ¿Deseas registrar el movimiento?",
    # Remaining page copy, empty states, labels and accessibility text
    "Key figures": "Cifras principales", "Find a vendor": "Buscar proveedor",
    "Print the full business overview, or open a customer or vendor statement from the tables below.": "Imprime el resumen completo del negocio o abre el estado de cuenta de un cliente o proveedor en las tablas de abajo.",
    "Perfumería Lamus — Business overview": "Perfumería Lamus — Resumen del negocio",
    "As of": "Al", "Customer": "Cliente", "Vendor": "Proveedor", "Entry": "Movimiento",
    "Note": "Nota", "Added": "Agregado", "Removed": "Retirado", "Set": "Establecido",
    "No customers on file.": "No hay clientes registrados.", "No vendors on file.": "No hay proveedores registrados.",
    "No bank history.": "No hay historial bancario.", "Business overview": "Resumen del negocio",
    "Print": "Imprimir", "No results found.": "No se encontraron resultados.",
    "No customers match these filters.": "Ningún cliente coincide con estos filtros.",
    "No vendors match these filters.": "Ningún proveedor coincide con estos filtros.",
    "Search customers": "Buscar clientes", "Search vendors": "Buscar proveedores",
    "What is this movement for?": "¿Cuál es el motivo de este movimiento?",
    "e.g. Assorted fragrances — 24 units": "Ej.: fragancias surtidas — 24 unidades",
    "Invoice number, order details…": "Número de factura, detalles del pedido…",
    "Invoice or transfer reference…": "Referencia de factura o transferencia…",
    "e.g. Eau de parfum 100 ml": "Ej.: perfume de 100 ml",
    "Anything worth remembering about this sale": "Información importante sobre esta venta",
    "Receipt number, who paid, etc.": "Número de recibo, quién pagó, etc.",
    # User-facing server and validation messages
    "Security check failed. Refresh the page and try again.": "La verificación de seguridad falló. Actualiza la página e inténtalo de nuevo.",
    "You were signed out after 30 minutes of inactivity.": "Tu sesión se cerró después de 30 minutos de inactividad.",
    "That file is too large. Choose a Lamus backup under 25 MB.": "El archivo es demasiado grande. Elige una copia de Lamus de menos de 25 MB.",
    "Too many attempts. Wait 15 minutes, then try again.": "Demasiados intentos. Espera 15 minutos y vuelve a intentarlo.",
    "Invalid username or password.": "El usuario o la contraseña no son correctos.",
    "The username or recovery code is not valid.": "El usuario o el código de recuperación no son válidos.",
    "Password must be at least 8 characters.": "La contraseña debe tener mínimo 8 caracteres.",
    "Passwords do not match.": "Las contraseñas no coinciden.",
    "Password updated. Please log in.": "Contraseña actualizada. Inicia sesión.",
    "Your current password is incorrect.": "La contraseña actual no es correcta.",
    "New password must be at least 8 characters.": "La contraseña nueva debe tener mínimo 8 caracteres.",
    "New passwords do not match.": "Las contraseñas nuevas no coinciden.",
    "Password changed successfully.": "La contraseña se cambió correctamente.",
    "New recovery code created. Save it now; it will not be shown again.": "Se creó un código de recuperación nuevo. Guárdalo ahora; no volverá a mostrarse.",
    "Customer added.": "Cliente agregado.", "Customer updated.": "Cliente actualizado.",
    "Credit sale recorded.": "Venta a crédito registrada.", "Payment recorded.": "Pago registrado.",
    "Ledger entry updated and balances recalculated.": "Movimiento actualizado y saldos recalculados.",
    "Entry voided. The balance has been recalculated.": "Movimiento anulado. El saldo fue recalculado.",
    "Customer archived.": "Cliente archivado.", "Vendor added.": "Proveedor agregado.",
    "Vendor updated.": "Proveedor actualizado.", "Stock purchase recorded.": "Compra de inventario registrada.",
    "Vendor payment recorded.": "Pago al proveedor registrado.", "Vendor archived.": "Proveedor archivado.",
    "Bank movement recorded.": "Movimiento bancario registrado.",
    "Type RESTORE exactly to confirm.": "Escribe RESTAURAR exactamente para confirmar.",
    "Backup restored. Please sign in again.": "Copia restaurada. Inicia sesión de nuevo.",
    "Opening balance was not a valid number — account created without it.": "El saldo inicial no era un número válido; la cuenta se creó sin ese saldo.",
    "Payment must be positive": "El pago debe ser mayor que cero",
    "Customer has no outstanding balance": "El cliente no tiene saldo pendiente",
    "Payment exceeds customer balance": "El pago supera el saldo del cliente",
    "Amount must be positive": "El valor debe ser mayor que cero",
    "This account has no balance to reduce": "Esta cuenta no tiene saldo por reducir",
    "That is more than the current balance": "El valor supera el saldo actual",
    "This edit would make a payment exceed the balance available at that time": "Esta edición haría que el pago supere el saldo disponible en ese momento",
    "Multi-item entries cannot be edited from this screen": "Los movimientos con varios artículos no se pueden editar desde esta pantalla",
    "Entry not found": "No se encontró el movimiento", "Voided entries cannot be edited": "Los movimientos anulados no se pueden editar",
    "This entry type cannot be edited": "Este tipo de movimiento no se puede editar",
    "This entry is already voided": "Este movimiento ya está anulado",
    "Vendor has no outstanding payable": "No hay saldo pendiente con este proveedor",
    "Payment exceeds vendor balance": "El pago supera el saldo del proveedor",
    "Nothing is payable to reduce": "No hay saldo por pagar para reducir",
    "That is more than the current payable": "El valor supera el saldo por pagar actual",
    "At least one line item is required": "Debes agregar al menos un artículo",
    "Each item needs a name": "Cada artículo necesita un nombre",
    "Item price and quantity must be positive": "El precio y la cantidad deben ser mayores que cero",
    "Invalid bank action": "Acción bancaria no válida",
    "A note is required when removing money": "Debes escribir una nota al retirar dinero",
    "The database safety check failed.": "Falló la verificación de seguridad de la base de datos.",
    "The backup file is too large.": "El archivo de copia es demasiado grande.",
    "This encrypted backup was created on a different computer.": "Esta copia cifrada se creó en otro computador.",
    "This is not a complete Lamus backup.": "Esta no es una copia completa de Lamus.",
    "The backup expands beyond the safe size limit.": "La copia supera el límite de tamaño seguro.",
    "This backup belongs to a different application.": "Esta copia pertenece a otra aplicación.",
    "The selected file is not a valid Lamus backup.": "El archivo seleccionado no es una copia válida de Lamus.",
    "Choose a Lamus backup file first.": "Primero elige un archivo de copia de Lamus.",
    "The backup is damaged and cannot be restored.": "La copia está dañada y no se puede restaurar.",
    "The backup is incomplete and cannot be restored.": "La copia está incompleta y no se puede restaurar.",
    # Complete screen and generated-label coverage
    "Open account": "Abrir cuenta", "Payment received": "Pago recibido",
    "Credit sale": "Venta a crédito", "Stock purchase": "Compra de inventario",
    "Payment sent": "Pago enviado",
    "No customer matches that search. Try a shorter part of the name or phone number.": "Ningún cliente coincide con la búsqueda. Prueba con una parte más corta del nombre o teléfono.",
    "No customer matches this search or filter. Clear the filter or try another spelling.": "Ningún cliente coincide con la búsqueda o el filtro. Limpia el filtro o prueba otra forma de escribirlo.",
    "No vendor matches that search. Try a shorter part of the name or phone number.": "Ningún proveedor coincide con la búsqueda. Prueba con una parte más corta del nombre o teléfono.",
    "No vendor matches this search or filter.": "Ningún proveedor coincide con la búsqueda o el filtro.",
    "Open a new customer account in the ledger.": "Abre una cuenta nueva para el cliente.",
    "Add customer": "Agregar cliente", "Back to customers": "Volver a clientes",
    "Already owed from before? Record it now as the first entry.": "¿Ya tenía un saldo anterior? Regístralo ahora como el primer movimiento.",
    "Add a supplier the store buys stock from.": "Agrega un proveedor al que el negocio le compra inventario.",
    "Add vendor": "Agregar proveedor", "Back to vendors": "Volver a proveedores",
    "Already owe this supplier? Record it now as the first entry.": "¿Ya le debes a este proveedor? Regístralo ahora como el primer movimiento.",
    "Money added to and taken from the store's account, with a note for every movement.": "Dinero que entra y sale de la cuenta del negocio, con una nota en cada movimiento.",
    "Printable history": "Historial para imprimir", "Record a movement": "Registrar un movimiento",
    "Add money to the account": "Agregar dinero a la cuenta",
    "A note is required when taking money out.": "Debes escribir una nota al retirar dinero.",
    "this is more than the current balance — the account will go negative. You'll be asked to confirm.": "este valor supera el saldo actual; la cuenta quedará en negativo. Se te pedirá confirmación.",
    "Movement history": "Historial de movimientos", "Newest first": "Más recientes primero",
    "Changed password": "Cambió la contraseña", "Reset forgotten password": "Restableció la contraseña olvidada",
    "Added customer": "Agregó un cliente", "Edited customer": "Editó un cliente",
    "Archived customer": "Archivó un cliente", "Recorded customer credit sale": "Registró una venta a crédito",
    "Recorded customer payment": "Registró un pago de cliente", "Recorded customer write-off": "Registró un ajuste de cliente",
    "Edited customer ledger entry": "Editó un movimiento de cliente", "Voided customer ledger entry": "Anuló un movimiento de cliente",
    "Added vendor": "Agregó un proveedor", "Edited vendor": "Editó un proveedor",
    "Archived vendor": "Archivó un proveedor", "Recorded vendor purchase": "Registró una compra a proveedor",
    "Recorded vendor payment": "Registró un pago a proveedor", "Recorded vendor credit": "Registró un ajuste de proveedor",
    "Edited vendor ledger entry": "Editó un movimiento de proveedor", "Voided vendor ledger entry": "Anuló un movimiento de proveedor",
    "Changed bank balance": "Cambió el saldo bancario", "Downloaded complete backup": "Descargó una copia completa",
    "Restored complete backup": "Restauró una copia completa",
    "Signed in": "Inició sesión", "Signed out": "Cerró sesión",
    "Created recovery code": "Creó un código de recuperación",
    "Account settled": "Cuenta al día", "Owed to the store": "Debe al negocio",
    "Owed by the store": "El negocio debe", "Balance after": "Saldo después",
    "This account has no movements. Record a credit sale or payment and it will appear here.": "Esta cuenta no tiene movimientos. Registra una venta a crédito o un pago y aparecerá aquí.",
    "New balance due": "Nuevo saldo pendiente",
    "This payment is larger than the balance due.": "Este pago supera el saldo pendiente.",
    "Update the details on this account. The ledger history is not affected.": "Actualiza los datos de esta cuenta. El historial no se modificará.",
    "Archive this customer": "Archivar este cliente", "Archive customer": "Archivar cliente",
    "Archive this vendor": "Archivar este proveedor", "Archive vendor": "Archivar proveedor",
    "Customer statement": "Estado de cuenta del cliente", "Vendor statement": "Estado de cuenta del proveedor",
    "Statement for": "Estado de cuenta de", "Supplier": "Proveedor", "Customer signature": "Firma del cliente",
    "Vendor signature": "Firma del proveedor", "Review edit": "Revisar edición",
    "Confirm and save": "Confirmar y guardar",
    "Backup & Recovery": "Copia y recuperación", "Last sign-in": "Último ingreso",
    "Add customer": "Agregar cliente", "Edit customer": "Editar cliente",
    "Add vendor": "Agregar proveedor", "Edit vendor": "Editar proveedor",
    "Record type": "Tipo de registro", "Record ID": "ID del registro",
    "Edit ": "Editar", "Archive ?": "¿Archivar esta cuenta?",
    "Hides  from the customers list and overviews. The ledger history is kept — nothing is deleted.": "Oculta esta cuenta de la lista y los resúmenes de clientes. El historial se conserva; no se elimina nada.",
    "— Customer statement": "— Estado de cuenta del cliente",
    "customers": "clientes", "vendors": "proveedores", "ledger": "cuentas de clientes",
    "vendor_ledger": "cuentas de proveedores", "users": "usuarios",
    "bank_balance_log": "movimientos bancarios", "audit_log": "auditoría",
    "Bad Request": "Solicitud no válida", "Not Found": "Página no encontrada",
    "The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.": "No se encontró la página solicitada. Revisa la dirección e inténtalo de nuevo.",
}


DYNAMIC_PATTERNS = [
    (re.compile(r"^(\d+) of (\d+) customers owe$"), r"\1 de \2 clientes deben"),
    (re.compile(r"^(\d+) payments received$"), r"\1 pagos recibidos"),
    (re.compile(r"^(\d+) credit sales recorded$"), r"\1 ventas a crédito registradas"),
    (re.compile(r"^(\d+) recorded actions$"), r"\1 acciones registradas"),
    (re.compile(r"^(\d+) sign-ins$"), r"\1 ingresos"),
    (re.compile(r"^Last sign-in (.+)$"), r"Último ingreso \1"),
    (re.compile(r"^Last (\d+) movements$"), r"Últimos \1 movimientos"),
    (re.compile(r"^Last (\d+) entries$"), r"Últimos \1 movimientos"),
    (re.compile(r"^(\d+) customer(s)? owe$"), r"\1 clientes deben"),
    (re.compile(r"^(\d+) vendor(s)? on file$"), r"\1 proveedores registrados"),
    (re.compile(r"^As of (.+)$"), r"Al \1"),
    (re.compile(r"^Opening balance skipped: (.+)$"), r"Se omitió el saldo inicial: \1"),
    (re.compile(r"^Last payment (.+)$"), r"Último pago: \1"),
    (re.compile(r"^(\d+) of (\d+) vendors owed$"), r"Se debe a \1 de \2 proveedores"),
    (re.compile(r"^(\d+) entries · newest first$"), r"\1 movimientos · más recientes primero"),
    (re.compile(r"^1 entry · newest first$"), r"1 movimiento · más reciente primero"),
    (re.compile(r"^Edit (.+)$"), r"Editar \1"),
    (re.compile(r"^Pay full balance · (.+)$"), r"Pagar saldo completo · \1"),
    (re.compile(r"^Pay full payable · (.+)$"), r"Pagar todo lo pendiente · \1"),
    (re.compile(r"^Issued (.+)$"), r"Emitido el \1"),
    (re.compile(r"^Generated (.+)$"), r"Generado el \1"),
    (re.compile(r"^Prepared (.+)$"), r"Preparado el \1"),
    (re.compile(r"^Account since (.+)$"), r"Cuenta desde el \1"),
    (re.compile(r"^Payable as of (.+)$"), r"Saldo por pagar al \1"),
    (re.compile(r"^Balance due as of (.+)$"), r"Saldo pendiente al \1"),
    (re.compile(r"^Account nº (.+)$"), r"Cuenta n.º \1"),
    (re.compile(r"^Amount: (.+)$"), r"Valor: \1"),
    (re.compile(r"^Archive (.+)\?$"), r"¿Archivar a \1?"),
    (re.compile(r"^Hides (.+) from the customers list and overviews\. The ledger history is kept — nothing is deleted\.$"), r"Oculta a \1 de la lista y los resúmenes de clientes. El historial se conserva; no se elimina nada."),
    (re.compile(r"^Hides (.+) from the vendors list and overviews\. The ledger history is kept — nothing is deleted\.$"), r"Oculta a \1 de la lista y los resúmenes de proveedores. El historial se conserva; no se elimina nada."),
    (re.compile(r"^They'll drop out of the customers list and overviews\..+$"), r"Dejará de aparecer en la lista y los resúmenes de clientes. El historial se conservará."),
    (re.compile(r"^They'll drop out of the vendors list and overviews\..+$"), r"Dejará de aparecer en la lista y los resúmenes de proveedores. El historial se conservará."),
    (re.compile(r"^OWNER TOOLS · (.+)$"), r"HERRAMIENTAS DEL PROPIETARIO · \1"),
    (re.compile(r"^OWNER SETTINGS · (.+)$"), r"CONFIGURACIÓN DEL PROPIETARIO · \1"),
    (re.compile(r"^(.+) — Customer statement$"), r"\1 — Estado de cuenta del cliente"),
    (re.compile(r"^(.+) — Vendor statement$"), r"\1 — Estado de cuenta del proveedor"),
]


def translate_text(value, locale):
    if locale != "es_CO" or not value:
        return value
    if value in ES:
        return ES[value]
    if value.endswith(" · Perfumería Lamus"):
        prefix = value.removesuffix(" · Perfumería Lamus")
        return f"{translate_text(prefix, locale)} · Perfumería Lamus"
    for pattern, replacement in DYNAMIC_PATTERNS:
        if pattern.match(value):
            return pattern.sub(replacement, value)
    return value


def localize_html(html, locale):
    if locale != "es_CO":
        return html
    soup = BeautifulSoup(html, "html.parser")
    if soup.html:
        soup.html["lang"] = "es-CO"
    for node in soup.find_all(string=True):
        if node.parent and node.parent.name in {"script", "style"}:
            continue
        raw = str(node)
        stripped = raw.strip()
        translated = translate_text(stripped, locale)
        if translated != stripped:
            node.replace_with(raw.replace(stripped, translated))
    for element in soup.find_all(True):
        for attribute in ("placeholder", "aria-label", "title"):
            if element.has_attr(attribute):
                element[attribute] = translate_text(element[attribute], locale)
    return str(soup)


def format_cop(value, locale):
    return format_currency(
        int(round(float(value or 0))),
        "COP",
        locale=locale,
        currency_digits=False,
        format="¤#,##0",
    ).replace("COP", "$")


def parse_stored_datetime(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value)[:19], fmt)
        except ValueError:
            continue
    return None


def format_day(value, locale):
    parsed = parse_stored_datetime(value)
    return babel_date(parsed, format="d MMM yyyy", locale=locale) if parsed else (value or "—")


def format_moment(value, locale):
    parsed = parse_stored_datetime(value)
    return babel_datetime(parsed, format="d MMM yyyy · HH:mm", locale=locale) if parsed else (value or "—")
