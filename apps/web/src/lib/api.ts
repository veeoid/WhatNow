const API_URL = "http://localhost:5000";

export const getPlan = async (data: any) => {
	const response = await fetch(`${API_URL}/plan`, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
		},
		body: JSON.stringify(data),
	});
	return response.json();
};
