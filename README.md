# 🥞🦜 askFSDL 🦜🥞

askFSDL is a demonstration of a retrieval-augmented question-answering application.

You can try it out via the Discord bot frontend in the
[Full Stack Discord](https://fsdl.me/join-discord-askfsdl)!

We use our educational materials as a corpus:
the [Full Stack LLM Bootcamp](https://fullstackdeeplearning.com/llm-bootcamp),
the [Full Stack Deep Learning course](https://fullstackdeeplearning.com/course).

So the resulting application is great at answering questions like

- What are the differences between PyTorch, TensorFlow, and JAX?
- How do I build an ML team?
- Which is cheaper: running experiments on cheap, slower GPUs or fast, more expensive GPUs?
- What's a data flywheel?

## Stack

We use [`langchain`](https://github.com/hwchase17/langchain)
to organize our LLM invocations and prompt magic.

We stood up a MongoDB instance on
[Atlas](https://www.mongodb.com/atlas/database)
to store our cleaned and organized document corpus.
See the `Running ETL to Build the Document Corpus` notebook.

For fast search of relevant documents to insert into our prompt,
we use a [FAISS index](https://github.com/facebookresearch/faiss).

We host the application backend on
[Modal](https://modal.com/),
which provides serverless execution and scaling.
That's also where we execute batch jobs,
like writing to the document store and refreshing the vector index.

We host the Discord bot,
written in [`discord.py`](https://discordpy.readthedocs.io/en/stable/),
on a free-tier
[AWS EC2](https://aws.amazon.com/ec2/)
instance,
which we provision and configure with
[Pulumi](https://www.pulumi.com/).

We use
[Gantry](https://gantry.io)
to monitor model behvaior in production and collect feedback from users.
