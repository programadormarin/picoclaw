import { createAgent } from './agent.js';
import { defaultTools } from './tools.js';
import { findModels } from './models.js';

async function main() {
    // Discover cheap models
    console.log('🔍 Discovering cheap models...');
    const cheapModels = await findModels({ maxPromptPrice: 0.0005 });
    if (cheapModels.length > 0) {
        console.log('Available cheap models:', cheapModels.slice(0, 5).map(m => m.id).join(', '));
    }

    const agent = createAgent({
        apiKey: process.env.OPENROUTER_API_KEY || 'sk-or-',
        model: 'openrouter/auto',
        instructions: 'You are a helpful assistant with access to tools.',
        tools: defaultTools,
    });

    // Hook into events
    agent.on('thinking:start', () => console.log('\n🤔 Thinking...'));
    agent.on('tool:call', (name, args) => console.log(`🔧 Using ${name}:`, args));
    agent.on('stream:delta', (delta) => process.stdout.write(delta));
    agent.on('stream:end', () => console.log('\n'));
    agent.on('error', (err) => console.error('❌ Error:', err.message));

    // Interactive loop
    const readline = await import('readline');
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    console.log('Agent ready. Type your message (Ctrl+C to exit):\n');

    const prompt = () => {
        rl.question('You: ', async (input: string) => {
            if (!input.trim()) {
                prompt();
                return;
            }
            await agent.send(input);
            prompt();
        });
    };

    prompt();
}

main().catch(console.error);
