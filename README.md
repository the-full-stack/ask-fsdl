# 🥞🦜 askFSDL 🦜🥞

askFSDL is a demonstration of a retrieval-augmented question-answering application.

You can try it out via the Discord bot frontend in the
[Full Stack Discord](https://fsdl.me/join-discord-askfsdl)!

We use our educational materials as a corpus:
the [Full Stack LLM Bootcamp](https://fullstackdeeplearning.com/llm-bootcamp),
the [Full Stack Deep Learning course](https://fullstackdeeplearning.com/course), and
the [Opinionated LLM++ Lit Review](https://tfs.ai/llm-lit-review).

So the resulting application is great at answering questions like

- Which is cheaper: running experiments on cheap, slower GPUs or fast, more expensive GPUs?
- How do I build an ML team?
- What's a data flywheel?
- Should I use a dedicated vector store for my embeddings?
- What is zero-shot chain-of-thought reasoning?

## EXPERIMENTAL: run it yourself

This project is under rapid development, so expect sharp edges
while setting it up in your environment.

Thanks to community contributions,
we can share a best-effort guide to running the application yourself
[here](./setup/).

Note that this application uses cloud services.
For most of these services, regular usage of the app will fall under the free tier.
However, OpenAI API calls can easily become expensive,
so make sure to se
[usage limits](https://platform.openai.com/account/billing/limits)
to prevent surprise bills.

## Stack

We use [`langchain`](https://github.com/hwchase17/langchain)
to organize our LLM invocations and prompt magic.

We stood up a MongoDB instance on
[Atlas](https://www.mongodb.com/atlas/database)
to store our cleaned and organized document corpus.
See the `Running ETL to Build the Document Corpus` notebook for details.

For fast search of relevant documents to insert into our prompt,
we use a [FAISS index](https://github.com/facebookresearch/faiss).

We host the application backend on
[Modal](https://modal.com/),
which provides serverless execution and scaling.
That's also where we execute batch jobs,
like writing to the document store and refreshing the vector index.

For creating a simple user interface in pure Python,
we use [Gradio](https://gradio.app/).
This UI is great for quick tests without deploying a full frontend
but with a better developer experience than curl-ing from the command line.

We host the Discord bot on
[Modal](https://modal.com/)
as well, relying on Discord's
[interactions endpoints](https://discord.com/developers/docs/tutorials/upgrading-to-application-commands#adding-an-interactions-endpoint-url)
to run the bot serverlessly.

We use
[Gantry](https://gantry.io)
to monitor model behvaior in production and collect feedback from users.
