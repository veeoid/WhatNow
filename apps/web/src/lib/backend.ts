/** Local backend address, used only when BACKEND_URL is absent during development. */
const LOCAL_BACKEND_URL = "http://127.0.0.1:5001";

/**
 * Resolve the planning backend's base URL.
 *
 * Falling back to localhost in production is worse than failing: the request dies with a
 * connection error that reads like "the backend is down" when the real cause is an unset
 * environment variable. So production demands the variable be set.
 */
export function getBackendUrl(): string {
	const configured = process.env.BACKEND_URL?.trim();
	if (configured) {
		return configured.replace(/\/+$/, "");
	}
	if (process.env.NODE_ENV === "production") {
		throw new Error("BACKEND_URL is not set");
	}
	return LOCAL_BACKEND_URL;
}
