import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
	plugins: [react()],
	base: "./",
	build: {
		outDir: "../web",
		emptyOutDir: true,
	},
	server: {
		proxy: {
			"/eel.js": {
				target: "http://localhost:5000",
				ws: true,
			},

			'/eel': {
				target: 'http://localhost:5000',
				ws: true,
			}
		},
	},
});
