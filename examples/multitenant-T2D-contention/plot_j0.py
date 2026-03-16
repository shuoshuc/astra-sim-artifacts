import matplotlib.pyplot as plt

# J0 completion time (ns) as a function of number of contention jobs
data = {
    0: 12548235294,
    1: 12548235294,
    2: 12820211602,
    3: 12820212082,
    4: 12822949654,
}

x = sorted(data.keys())
y = [data[k] / 1e9 for k in x]  # convert ns -> s

fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(x, y, marker="o", linewidth=2, markersize=7, color="steelblue")

ax.set_xlabel("Number of contention jobs", fontsize=13)
ax.set_ylabel("J0 completion time (s)", fontsize=13)
ax.set_title("J0 JCT vs. number of contention jobs", fontsize=14)
ax.set_xticks(x)
ax.grid(axis="y", linestyle="--", alpha=0.6)

plt.tight_layout()
plt.savefig("j0_jct.png", dpi=150)
print("Saved j0_jct.png")
