export interface OpenRouterModel {
    id: string;
    name: string;
    description?: string;
    context_length: number;
    pricing: { prompt: string; completion: string };
    top_provider?: { is_moderated: boolean };
}

export async function fetchModels(): Promise<OpenRouterModel[]> {
    const res = await fetch('https://openrouter.ai/api/v1/models');
    const data = await res.json();
    return data.data;
}

// Find models by criteria
export async function findModels(filter: {
    author?: string;      // e.g., 'anthropic', 'openai', 'google'
    minContext?: number;  // e.g., 100000 for 100k context
    maxPromptPrice?: number; // e.g., 0.001 for cheap models
}): Promise<OpenRouterModel[]> {
    const models = await fetchModels();

    return models.filter((m) => {
        if (filter.author && !m.id.startsWith(filter.author + '/')) return false;
        if (filter.minContext && m.context_length < filter.minContext) return false;
        if (filter.maxPromptPrice) {
            const price = parseFloat(m.pricing.prompt);
            if (price > filter.maxPromptPrice) return false;
        }
        return true;
    });
}
