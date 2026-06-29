interface Eel {
	// Defina aqui as funções que você expôs no Python
	hello_from_python: () => void;

	// Permite expor funções do JS para o Python
	expose: (fn: Function, name: string) => void;
}

interface Window {
	eel: Eel;
}
