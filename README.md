# 🥞🦜 askFSDL 🦜🥞

askFSDL is a demonstration of a document-backed question-answering pipeline.

We use the materials from the
[Full Stack Deep Learning course](https://fullstackdeeplearning.com/course)
as our document corpus,
so the resulting application is great at answering questions like

- What are the differences between PyTorch, TensorFlow, and JAX?
- How do I build an ML team?
- Which is cheaper: running experiments on cheap, slower GPUs or fast, more expensive GPUs?
- What's a data flywheel?

You can try it out via the Discord bot frontend in the
[FSDL Discord](https://fsdl.me/join-discord).

## Stack

We use [`langchain`](https://github.com/hwchase17/langchain)
to organize our LLM invocations and prompt magic.

We stood up a MongoDB instance on
[Atlas](https://www.mongodb.com/atlas/database)
to store our cleaned and organized document corpus,
as shown in the "Building the FSDL Corpus" notebook.

For fast search of relevant documents to insert into our prompt,
we use a [FAISS index](https://github.com/facebookresearch/faiss).

We host the application backend,
which communicates with
[OpenAI's language modeling API](https://openai.com/api/)
and other services, on
[Modal](https://modal.com/),
which provides serverless execution and scaling.
That's also where we execute batch jobs,
like syncing the document and vector stores.

We host the Discord bot,
written in [`py-cord`](https://docs.pycord.dev/en/stable/),
on a free-tier
[AWS EC2](https://aws.amazon.com/ec2/)
instance.

We use
[Gantry](https://gantry.io)
to monitor model behvaior in production and collect feedback from users.
